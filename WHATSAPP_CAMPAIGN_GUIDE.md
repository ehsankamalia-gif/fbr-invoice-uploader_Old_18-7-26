# WhatsApp Campaign Management Guide

## Overview
The WhatsApp Campaign Management system provides a robust way to manage bulk messaging campaigns with features for delivery reliability, security, and auditing.

## Key Features

### 1. Secure Campaign Deletion (Soft Delete)
- **Mechanism:** Campaigns are not permanently removed from the database. Instead, they are marked as `is_deleted = True`.
- **Safety:** Deleting a campaign automatically cancels all pending messages in that campaign.
- **Audit Trail:** Every deletion is logged in the `AuditLog` table with the timestamp, user ID, and campaign details.
- **How to use:** 
  - Go to the **Campaign History** tab.
  - Right-click on a campaign.
  - Select **Delete Campaign (Soft Delete)**.
  - Confirm the action in the dialog.

### 2. Automated Retry System
- **Exponential Backoff:** Failed messages due to temporary issues (network, server errors) are automatically re-queued for retry.
- **Retry Intervals:** The delay increases exponentially (5m, 10m, 20m...) up to a maximum of 24 hours.
- **Retry Limits:** By default, messages are retried up to 3 times before being marked as permanently failed.
- **Manual Retry:** You can manually trigger a retry for all failed messages in a campaign via the context menu in the history table.

### 3. Monitoring & Auditing
- **Real-time Progress:** The progress bar updates in real-time as messages are sent or re-queued for retry.
- **Detailed History:** Double-click any row in the **Campaign Details** view to see the full retry history for a specific message, including error codes and timestamps.
- **Audit Logs:** All major actions (Create, Start, Delete, Retry All) are recorded in the `audit_logs` database table for administrative review.

## Lifecycle Management

### 1. Starting/Resuming a Campaign
- **Validation:** Before activation, the system checks for:
    - **Targeting:** At least one recipient must be present.
    - **Creative Assets:** The message template must be provided and meet minimum length requirements.
- **Audit:** Start actions are logged with a timestamp and the initiating user.
- **Visual Indicator:** The campaign status updates to **RUNNING** and progress monitoring begins.

### 2. Pausing a Campaign
- **Functionality:** Immediately stops delivery for the current campaign.
- **Validation:** Only running campaigns can be paused.
- **Audit:** The pause action captures the stop reason (e.g., "User manual stop") and timestamp.
- **Visual Indicator:** The status updates to **PAUSED**. You can resume it at any time.

### 3. State Transition Rules
- **PENDING/PAUSED/FAILED** → **RUNNING** (Valid)
- **RUNNING** → **PAUSED** (Valid)
- **COMPLETED** → **RUNNING** (Invalid - create a new campaign instead)
- **CANCELLED** → **RUNNING** (Valid - resumes unsent messages)

## Troubleshooting

### Common Error Codes
- **400 (Bad Request):** Usually means the phone number is invalid or not registered on WhatsApp.
- **401 (Unauthorized):** Check your Evolution API Key in settings.
- **404 (Not Found):** The WhatsApp instance name might be incorrect or the instance is disconnected.
- **500/503 (Server Error):** Temporary issue with the Evolution API or WhatsApp servers. These will trigger an automated retry.

### Connection Issues
If the status is stuck in "Initialize" or "OFFLINE":
1. Go to the **Whatsapp Module** (QR Code page).
2. Click **Reset Instance** to refresh the connection.
3. Scan the QR code again if prompted.

### Bulk Sending Paused
If bulk sending stops unexpectedly:
1. Check your internet connection.
2. Ensure the WhatsApp instance status is "open".
3. Check the **Campaign History** to see if the campaign status is "RUNNING". If not, right-click and select **Retry Failed Messages**.

## Technical Details for Administrators
- **Database Tables:** `sms_campaigns`, `sms_queue`, `audit_logs`.
- **Retry Field:** `SMSQueue.next_retry_at` determines when the background worker will next attempt to send a failed message.
- **Soft Delete Field:** `SMSCampaign.is_deleted` and `SMSCampaign.deleted_at`.
