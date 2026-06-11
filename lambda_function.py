import os
import html
import boto3
from datetime import datetime, timezone

ses = boto3.client("ses")
dynamodb = boto3.resource("dynamodb")

DEDUPE_TABLE = os.environ["DEDUPE_TABLE"]
FROM_EMAIL = os.environ["FROM_EMAIL"]
TO_EMAILS = [x.strip() for x in os.environ["TO_EMAILS"].split(",") if x.strip()]
ENVIRONMENT = os.environ.get("ENVIRONMENT", "dev")

table = dynamodb.Table(DEDUPE_TABLE)

ALLOWED_SERVICES = {
    "EKS",
    "EC2",
    "APIGATEWAY",
    "ELASTICLOADBALANCING",
    "EBS",
    "EFS"
}

IMPORTANT_KEYWORDS = [
    "EKS",
    "KUBERNETES",
    "ADDON",
    "ADD-ON",
    "CSI",
    "EBS_CSI",
    "EFS_CSI",
    "DRIVER",
    "EC2",
    "INSTANCE",
    "RETIREMENT",
    "APIGATEWAY",
    "API_GATEWAY",
    "API GATEWAY",
    "SDK",
    "VERSION",
    "UPGRADE",
    "DEPRECATION",
    "DEPRECATED",
    "MAINTENANCE",
    "PATCH",
    "TLS",
    "CERTIFICATE",
    "ENDPOINT"
]


def lambda_handler(event, context):
    print("Received event:", event)

    detail = event.get("detail", {})

    account_id = detail.get("affectedAccount") or event.get("account", "unknown")
    service = detail.get("service", "UNKNOWN")
    event_type_code = detail.get("eventTypeCode", "UNKNOWN")
    event_category = detail.get("eventTypeCategory", "UNKNOWN")
    event_arn = detail.get("eventArn", event.get("id", "UNKNOWN"))
    communication_id = detail.get("communicationId", event.get("id", "UNKNOWN"))

    region = detail.get("eventRegion") or event.get("region", "global")
    status_code = detail.get("statusCode", "UNKNOWN")
    start_time = detail.get("startTime", "N/A")
    end_time = detail.get("endTime", "N/A")
    last_updated_time = detail.get("lastUpdatedTime", event.get("time", "N/A"))

    description = extract_description(detail)
    affected_entities = extract_affected_entities(detail)
    affected_zones = extract_affected_zones(detail, affected_entities)
    resource_name = detect_resource_name(affected_entities, description)

    if not should_alert(service, event_type_code, event_category, description, affected_entities):
        print("Ignored: event did not match DEV AWS Health filters")
        return {"status": "ignored"}

    dedupe_id = f"{account_id}#{communication_id}#{event_arn}"

    if is_duplicate(dedupe_id):
        print(f"Duplicate skipped: {dedupe_id}")
        return {"status": "duplicate_skipped"}

    severity = calculate_severity(event_category, event_type_code, description, status_code)

    subject = (
        f"[{ENVIRONMENT.upper()}][AWS Health][{service}][{severity}] "
        f"{event_type_code} - {region}"
    )

    html_body = build_html_email(
        env=ENVIRONMENT,
        account_id=account_id,
        region=region,
        service=service,
        event_type_code=event_type_code,
        event_category=event_category,
        severity=severity,
        status_code=status_code,
        notification_time=last_updated_time,
        schedule_start=start_time,
        schedule_end=end_time,
        affected_zones=affected_zones,
        affected_entities=affected_entities,
        resource_name=resource_name,
        description=description,
        event_arn=event_arn,
        communication_id=communication_id
    )

    ses.send_email(
        Source=FROM_EMAIL,
        Destination={"ToAddresses": TO_EMAILS},
        Message={
            "Subject": {
                "Data": subject,
                "Charset": "UTF-8"
            },
            "Body": {
                "Html": {
                    "Data": html_body,
                    "Charset": "UTF-8"
                },
                "Text": {
                    "Data": description,
                    "Charset": "UTF-8"
                }
            }
        }
    )

    save_dedupe_id(dedupe_id)

    print("Email sent:", subject)
    return {"status": "email_sent", "subject": subject}


def extract_description(detail):
    event_description = detail.get("eventDescription", [])

    if isinstance(event_description, list) and event_description:
        return event_description[0].get("latestDescription", "No description available")

    if isinstance(event_description, dict):
        return event_description.get("latestDescription", "No description available")

    return "No description available"


def extract_affected_entities(detail):
    entities = []

    for entity in detail.get("affectedEntities", []) or []:
        entities.append({
            "entityValue": entity.get("entityValue", "N/A"),
            "entityArn": entity.get("entityArn", "N/A"),
            "status": entity.get("status", "UNKNOWN"),
            "lastUpdatedTime": entity.get("lastUpdatedTime", "N/A")
        })

    if not entities:
        for resource in detail.get("resources", []) or []:
            entities.append({
                "entityValue": resource,
                "entityArn": "N/A",
                "status": "UNKNOWN",
                "lastUpdatedTime": "N/A"
            })

    return entities


def extract_affected_zones(detail, affected_entities):
    zones = set()
    metadata = detail.get("eventMetadata", {}) or {}

    for key, value in metadata.items():
        key_lower = key.lower()
        if "zone" in key_lower or "az" in key_lower:
            zones.add(str(value))

    for entity in affected_entities:
        value = entity.get("entityValue", "")
        if "ap-south-1a" in value:
            zones.add("ap-south-1a")
        if "ap-south-1b" in value:
            zones.add("ap-south-1b")
        if "ap-south-1c" in value:
            zones.add("ap-south-1c")
        if "us-east-1a" in value:
            zones.add("us-east-1a")
        if "us-east-1b" in value:
            zones.add("us-east-1b")
        if "us-east-1c" in value:
            zones.add("us-east-1c")

    return sorted(zones) if zones else ["N/A"]


def detect_resource_name(affected_entities, description):
    for entity in affected_entities:
        value = entity.get("entityValue", "")
        if value and value != "N/A":
            return value

    words = description.replace(",", " ").replace(".", " ").split()
    for word in words:
        if "eks" in word.lower() or "cluster" in word.lower() or "csi" in word.lower():
            return word

    return "N/A"


def should_alert(service, event_type_code, event_category, description, affected_entities):
    service_upper = service.upper()

    combined = " ".join([
        service,
        event_type_code,
        event_category,
        description,
        " ".join([e.get("entityValue", "") for e in affected_entities])
    ]).upper()

    if service_upper in ALLOWED_SERVICES:
        return True

    return any(keyword in combined for keyword in IMPORTANT_KEYWORDS)


def calculate_severity(event_category, event_type_code, description, status_code):
    value = f"{event_category} {event_type_code} {description} {status_code}".upper()

    if "ISSUE" in value or "OUTAGE" in value or "IMPAIRED" in value or "DEGRADED" in value:
        return "CRITICAL"

    if "SCHEDULEDCHANGE" in value or "RETIREMENT" in value:
        return "HIGH"

    if "DEPRECATION" in value or "UPGRADE" in value or "MAINTENANCE" in value:
        return "MEDIUM"

    return "INFO"


def is_duplicate(dedupe_id):
    response = table.get_item(Key={"dedupe_id": dedupe_id})
    return "Item" in response


def save_dedupe_id(dedupe_id):
    table.put_item(
        Item={
            "dedupe_id": dedupe_id,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
    )


def build_html_email(
    env,
    account_id,
    region,
    service,
    event_type_code,
    event_category,
    severity,
    status_code,
    notification_time,
    schedule_start,
    schedule_end,
    affected_zones,
    affected_entities,
    resource_name,
    description,
    event_arn,
    communication_id
):
    severity_color = {
        "CRITICAL": "#dc2626",
        "HIGH": "#ea580c",
        "MEDIUM": "#ca8a04",
        "INFO": "#2563eb"
    }.get(severity, "#2563eb")

    entity_rows = ""

    for entity in affected_entities:
        entity_rows += f"""
        <tr>
          <td style="padding:10px;border-bottom:1px solid #e5e7eb;">{html.escape(entity.get("entityValue", "N/A"))}</td>
          <td style="padding:10px;border-bottom:1px solid #e5e7eb;">{html.escape(entity.get("status", "UNKNOWN"))}</td>
          <td style="padding:10px;border-bottom:1px solid #e5e7eb;">{html.escape(entity.get("lastUpdatedTime", "N/A"))}</td>
        </tr>
        """

    if not entity_rows:
        entity_rows = """
        <tr>
          <td colspan="3" style="padding:10px;border-bottom:1px solid #e5e7eb;">No specific affected resource listed</td>
        </tr>
        """

    affected_zones_text = ", ".join([html.escape(zone) for zone in affected_zones])
    safe_description = html.escape(description).replace("\n", "<br>")

    return f"""
<!DOCTYPE html>
<html>
<body style="margin:0;background:#f3f4f6;font-family:Arial,Helvetica,sans-serif;color:#111827;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f3f4f6;padding:24px;">
    <tr>
      <td align="center">
        <table width="780" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:16px;overflow:hidden;border:1px solid #e5e7eb;">
          <tr>
            <td style="background:#111827;color:#ffffff;padding:28px;">
              <h1 style="margin:0;font-size:24px;">AWS Health Alert</h1>
              <p style="margin:8px 0 0;color:#d1d5db;font-size:14px;">DEV account notification</p>
            </td>
          </tr>

          <tr>
            <td style="padding:24px;">
              <span style="display:inline-block;background:{severity_color};color:#ffffff;padding:8px 16px;border-radius:999px;font-weight:bold;font-size:13px;">
                {html.escape(severity)}
              </span>

              <h2 style="margin:18px 0 6px;font-size:21px;">
                {html.escape(service)} - {html.escape(event_type_code)}
              </h2>

              <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;margin-top:16px;">
                <tr><td style="padding:12px;background:#f9fafb;border:1px solid #e5e7eb;"><b>Environment</b></td><td style="padding:12px;border:1px solid #e5e7eb;">{html.escape(env.upper())}</td></tr>
                <tr><td style="padding:12px;background:#f9fafb;border:1px solid #e5e7eb;"><b>AWS Account</b></td><td style="padding:12px;border:1px solid #e5e7eb;">{html.escape(account_id)}</td></tr>
                <tr><td style="padding:12px;background:#f9fafb;border:1px solid #e5e7eb;"><b>Region</b></td><td style="padding:12px;border:1px solid #e5e7eb;">{html.escape(region)}</td></tr>
                <tr><td style="padding:12px;background:#f9fafb;border:1px solid #e5e7eb;"><b>Affected Service</b></td><td style="padding:12px;border:1px solid #e5e7eb;">{html.escape(service)}</td></tr>
                <tr><td style="padding:12px;background:#f9fafb;border:1px solid #e5e7eb;"><b>Affected Zone</b></td><td style="padding:12px;border:1px solid #e5e7eb;">{affected_zones_text}</td></tr>
                <tr><td style="padding:12px;background:#f9fafb;border:1px solid #e5e7eb;"><b>Affected Resource</b></td><td style="padding:12px;border:1px solid #e5e7eb;">{html.escape(resource_name)}</td></tr>
                <tr><td style="padding:12px;background:#f9fafb;border:1px solid #e5e7eb;"><b>Event Category</b></td><td style="padding:12px;border:1px solid #e5e7eb;">{html.escape(event_category)}</td></tr>
                <tr><td style="padding:12px;background:#f9fafb;border:1px solid #e5e7eb;"><b>Status</b></td><td style="padding:12px;border:1px solid #e5e7eb;">{html.escape(status_code)}</td></tr>
                <tr><td style="padding:12px;background:#f9fafb;border:1px solid #e5e7eb;"><b>Notification Time</b></td><td style="padding:12px;border:1px solid #e5e7eb;">{html.escape(notification_time)}</td></tr>
                <tr><td style="padding:12px;background:#f9fafb;border:1px solid #e5e7eb;"><b>Scheduled Start</b></td><td style="padding:12px;border:1px solid #e5e7eb;">{html.escape(schedule_start)}</td></tr>
                <tr><td style="padding:12px;background:#f9fafb;border:1px solid #e5e7eb;"><b>Scheduled End</b></td><td style="padding:12px;border:1px solid #e5e7eb;">{html.escape(schedule_end)}</td></tr>
              </table>

              <h3 style="margin:26px 0 10px;font-size:17px;">Affected Resources</h3>

              <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;border:1px solid #e5e7eb;">
                <tr style="background:#f9fafb;">
                  <th align="left" style="padding:10px;border-bottom:1px solid #e5e7eb;">Resource</th>
                  <th align="left" style="padding:10px;border-bottom:1px solid #e5e7eb;">Status</th>
                  <th align="left" style="padding:10px;border-bottom:1px solid #e5e7eb;">Last Updated</th>
                </tr>
                {entity_rows}
              </table>

              <h3 style="margin:26px 0 10px;font-size:17px;">Event Details</h3>

              <div style="background:#f9fafb;border-left:5px solid {severity_color};padding:16px;border-radius:8px;line-height:1.6;font-size:14px;">
                {safe_description}
              </div>

              <p style="font-size:12px;color:#6b7280;margin-top:24px;">
                Event ARN: {html.escape(event_arn)}<br>
                Communication ID: {html.escape(communication_id)}
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
