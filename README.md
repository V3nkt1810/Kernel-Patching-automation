Kernel Patching Automation Script

This Python script automates the process of applying non-kernel patches to multiple Linux servers. It reads server details from an Excel sheet, connects to each server via SSH, and runs update commands concurrently. The script handles error reporting, tracks the patching status for each server, and sends a detailed email report upon completion, including the results in an Excel attachment.

Key Features:
Concurrent Server Patching: Executes patching commands on multiple servers concurrently using ThreadPoolExecutor.
SSH Connection Management: Attempts multiple SSH connections with retry logic for failed attempts.
Patching Status Tracking: Captures detailed patching results, including updated, installed, and removed packages for each server.
Email Notification: Sends an email with the patching status, attaching the results in an Excel file.
Logging: Logs all actions and errors to a log file for troubleshooting.
Compliance Calculation: Tracks cumulative patching progress across multiple patching sessions.
Custom Email Recipient List: Reads email addresses from a file, separating "TO" and "CC" fields for email notification.


Components:
Email Notifications: Sends HTML-formatted emails with the summary of the patching activity.
Error Handling: Includes SSH connection retries, and error logging for failed SSH sessions or commands.
Excel Sheet Parsing: Reads the list of servers from an Excel sheet and processes them in sequence, ensuring no server is processed twice.
Patching Summary: Reports the total number of servers patched, already patched servers, and overall compliance percentage.


Logging:
All events, errors, and patching statuses are logged into /root/Kernel_patching/patching.log for future reference.


Files:
patching.log: Log file capturing details of patching operations, SSH connections, and errors.
Excel file input: List of server names to be patched.
Email file input: List of recipients for patching summary emails.


This script is ideal for large-scale Linux patch management and ensures efficient and automated compliance tracking.
