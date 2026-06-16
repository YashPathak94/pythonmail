import os
import html
import boto3
from datetime import datetime, timezone

sns = boto3.client("sns")
dynamodb = boto3.resource("dynamodb")

DEDUPE_TABLE = os.environ["DEDUPE_TABLE"]
SNS_TOPIC_ARN = os.environ["SNS_TOPIC_ARN"]
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
        f"{event_type_code}"
    )

    # SNS subject has length restrictions, so keep it short.
    subject = subject[:100]

    message = build_sns_message(
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

    sns.publish(
        TopicArn=SNS_TOPIC_ARN,
        Subject=subject,
        Message=message
    )

    save_dedupe_id(dedupe_id)

    print("SNS email published:", subject)
    return {"status": "sns_published", "subject": subject}


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

    known_az_patterns = [
        "us-east-1a",
        "us-east-1b",
        "us-east-1c",
        "ap-south-1a",
        "ap-south-1b",
        "ap-south-1c"
    ]

    for entity in affected_entities:
        value = entity.get("entityValue", "")
        for az in known_az_patterns:
            if az in value:
                zones.add(az)

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


def build_sns_message(
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
    affected_resource_lines = []

    for entity in affected_entities:
        affected_resource_lines.append(
            f"- Resource: {entity.get('entityValue', 'N/A')}\n"
            f"  Status: {entity.get('status', 'UNKNOWN')}\n"
            f"  Last Updated: {entity.get('lastUpdatedTime', 'N/A')}"
        )

    if not affected_resource_lines:
        affected_resource_lines.append("- No specific affected resource listed")

    return f"""
AWS HEALTH ALERT - {env.upper()}

============================================================
SUMMARY
============================================================

Environment        : {env.upper()}
AWS Account        : {account_id}
Region             : {region}
Affected Service   : {service}
Affected Zone      : {", ".join(affected_zones)}
Affected Resource  : {resource_name}
Severity           : {severity}
Event Category     : {event_category}
Event Type Code    : {event_type_code}
Status             : {status_code}

============================================================
TIMING
============================================================

Notification Time  : {notification_time}
Scheduled Start    : {schedule_start}
Scheduled End      : {schedule_end}

============================================================
AFFECTED RESOURCES
============================================================

{chr(10).join(affected_resource_lines)}

============================================================
EVENT DETAILS
============================================================

{description}

============================================================
TRACKING
============================================================

Event ARN          : {event_arn}
Communication ID   : {communication_id}

============================================================
Generated by AWS Health → EventBridge → Lambda → SNS
============================================================
"""
