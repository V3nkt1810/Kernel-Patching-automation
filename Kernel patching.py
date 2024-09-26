import logging
import pandas as pd
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
import subprocess
import os
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import time

logging.basicConfig(
    filename='/root/Kernel_patching/patching.log',
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)

TRACKING_FILE = ''
FILE_PATH = ''
FROM_EMAIL = ""
EMAIL_FILE = ''
COUNT_FILE = ''
MAX_WORKERS = 100
TOTAL_SERVERS = 621
SSH_RETRY_DELAY = 120
MAX_SSH_RETRIES = 10

def get_last_processed_sheet():
    logging.info("Fetching last processed sheet.")
    if os.path.exists(TRACKING_FILE):
        with open(TRACKING_FILE, 'r') as file:
            return file.read().strip()
    return None

def save_last_processed_sheet(sheet_name):
    logging.info(f"Saving last processed sheet: {sheet_name}.")
    with open(TRACKING_FILE, 'w') as file:
        file.write(sheet_name)

def get_cumulative_patch_count():
    logging.info("Getting total patch count.")
    if os.path.exists(COUNT_FILE):
        with open(COUNT_FILE, 'r') as file:
            content = file.read().strip()
            if content:
                return int(content)
    return 0

def save_cumulative_patch_count(count):
    logging.info(f"Saving total patch count: {count}.")
    with open(COUNT_FILE, 'w') as file:
        file.write(str(count))

def read_email_addresses(file_path):
    logging.info("Reading email addresses.")
    with open(file_path, 'r') as file:
        lines = file.readlines()
    to_emails, cc_emails, current_list = [], [], None
    for line in lines:
        line = line.strip()
        if line == "[TO]":
            current_list = to_emails
        elif line == "[CC]":
            current_list = cc_emails
        elif current_list is not None and line:
            current_list.append(line)
    return to_emails, cc_emails

def send_email(subject, body, from_email, to_emails, cc_emails, attachment_bytes, attachment_name):
    logging.info(f"Sending email to: {', '.join(to_emails)} with CC: {', '.join(cc_emails)}")
    msg = MIMEMultipart()
    msg['From'] = from_email
    msg['To'] = ', '.join(to_emails)
    msg['Cc'] = ', '.join(cc_emails)
    msg['Subject'] = subject
    msg.attach(MIMEText(body, 'html'))
    
    part = MIMEBase('application', 'octet-stream')
    part.set_payload(attachment_bytes)
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f"attachment; filename={attachment_name}")
    msg.attach(part)
    
    try:
        process = subprocess.Popen(["sudo", "/usr/sbin/sendmail", "-t"], stdin=subprocess.PIPE)
        process.communicate(msg.as_string().encode('utf-8'))
        if process.returncode != 0:
            logging.error(f"Failed to send email. Process exited with code {process.returncode}")
    except Exception as e:
        logging.error(f"Failed to send email: {str(e)}")

def wait_for_ssh_connection(server):
    logging.info(f"Waiting for SSH connection to server: {server}.")
    for attempt in range(MAX_SSH_RETRIES):
        try:
            ssh_command = f'ssh -q -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=120 {server} "echo 1"'
            result = subprocess.run(ssh_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            if result.returncode == 0:
                logging.info(f"SSH connection to {server} established.")
                return True
            logging.warning(f"Attempt {attempt + 1} failed: {result.stderr.strip()}")
        except Exception as e:
            logging.error(f"Error waiting for SSH connection to {server} on attempt {attempt + 1}: {str(e)}")
        
        logging.info(f"Retrying SSH connection to {server} in {SSH_RETRY_DELAY // 60} minutes.")
        time.sleep(SSH_RETRY_DELAY)
    
    logging.error(f"Failed to establish SSH connection to {server} after {MAX_SSH_RETRIES} attempts.")
    return False

def run_command_on_server(server):
    logging.info(f"Running command on server: {server}.")
    commands = (
        "uname -r > /tmp/before_kernel_version"
        "rpm -qa > /tmp/kernel_patch ; "
        "subscription-manager refresh ; "
        "dnf update -y; "
        "rm -rf /var/cache/yum/ ; yum clean all; "
        "rpm -qa > /tmp/after_kernel_patch ; "
        "uname -r > /tmp/after_kernel_version"
        "echo 12345 | passwd --stdin root ; reboot "
    )
    
    if wait_for_ssh_connection(server):
        try:
            ssh_command = f'ssh -q -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=120 {server} "{commands}"'
            result = subprocess.run(ssh_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            logging.info(f"SSH command output for {server}: {result.stdout}")
            logging.info(f"SSH command error for {server}: {result.stderr}")
            
            if "Permission denied" in result.stderr:
                logging.warning(f'Server {server} - Password prompt or permission denied')
                return {'Server': server, 'Status': 'Password prompt or permission denied'}
            elif "Could not resolve hostname" in result.stderr or "Name or service not known" in result.stderr:
                logging.warning(f'Server {server} - Server not reachable')
                return {'Server': server, 'Status': 'Server not reachable'}
            elif result.returncode != 0:
                logging.error(f'Server {server} - {result.stderr.strip()}')
                return {'Server': server, 'Status': result.stderr.strip()}
            
            ssh_before_command = f'ssh -q -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=120 {server} "cat /tmp/before_non_kernel_patch"'
            before_patch_output = subprocess.run(ssh_before_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            before_packages = before_patch_output.stdout.splitlines()
            
            ssh_after_command = f'ssh -q -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=120 {server} "cat /tmp/after_non_kernel_patch"'
            after_patch_output = subprocess.run(ssh_after_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            after_packages = after_patch_output.stdout.splitlines()
            
            before_pkg_dict = {pkg.split('-')[0]: pkg for pkg in before_packages}
            after_pkg_dict = {pkg.split('-')[0]: pkg for pkg in after_packages}
            
            updated_packages = 0
            newly_installed_packages = 0
            removed_packages = 0
            current_date_str = datetime.now().strftime('%b %d')
            
            ssh_yum_log_command = f'ssh -q -o BatchMode=yes -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=120 {server} "cat /var/log/yum.log | grep \'{current_date_str}\'"'
            yum_log_output = subprocess.run(ssh_yum_log_command, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, universal_newlines=True)
            yum_log_content = yum_log_output.stdout.splitlines()
            
            for line in yum_log_content:
                if 'Updated:' in line:
                    updated_packages += 1
                elif 'Installed:' in line:
                    newly_installed_packages += 1
                elif 'Erased:' in line:
                    removed_packages += 1
            
            status = 'Patching Successful'
            if updated_packages == 0 and newly_installed_packages == 0 and removed_packages == 0:
                status = 'Already Patched'
            
            return {
                'Server': server,
                'Updated Packages': updated_packages,
                'Newly Installed Packages': newly_installed_packages,
                'Removed Packages': removed_packages,
                'Status': status
            }
        except Exception as e:
            logging.error(f'Server {server} - {str(e)}')
    
    return {'Server': server, 'Status': 'Connection Failed'}

def run_commands_on_servers_concurrently(servers):
    logging.info("Running commands on servers concurrently.")
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(run_command_on_server, server): server for server in servers}
        for future in as_completed(futures):
            results.append(future.result())
    return results

try:
    logging.info("Starting the patching process.")
    df = pd.read_excel(FILE_PATH, sheet_name=None, engine='openpyxl')
    last_processed_sheet = get_last_processed_sheet()
    sheets = sorted(df.keys())

    if last_processed_sheet:
        sheets = sheets[sheets.index(last_processed_sheet) + 1:]

    for sheet_name in sheets:
        logging.info(f"Processing sheet: {sheet_name}.")
        save_last_processed_sheet(sheet_name)
        
        sheet_df = df[sheet_name]
        servers = sheet_df['Server Name'].dropna().tolist()
        results = run_commands_on_servers_concurrently(servers)

        status_df = pd.DataFrame(results)
        successful_status_df = status_df[status_df['Status'] == 'Patching Successful']
        successful_patches = successful_status_df.shape[0]

        already_processed_hosts = set()
        unique_already_patched_count = 0
        for index, row in status_df.iterrows():
            if row['Status'] == 'Already Patched':
                if row['Server'] not in already_processed_hosts:
                    unique_already_patched_count += 1
                already_processed_hosts.add(row['Server'])

        cumulative_patches = get_cumulative_patch_count() + successful_patches + unique_already_patched_count
        compliance = (cumulative_patches / TOTAL_SERVERS) * 100

        if compliance >= 100:
            cumulative_patches = 0
        else:
            save_cumulative_patch_count(cumulative_patches)

        status_bytes = BytesIO()
        status_df.to_excel(status_bytes, index=False, engine='openpyxl')
        status_bytes.seek(0)

        email_subject = f"Kernel-Patching Status for: {sheet_name} servers"
        email_body = f"""
        <html>
            <head></head>
            <body>
                <p>Hi All,</p>
                <p>Non-Kernel Patching Completed for '{sheet_name}' servers. Please find the Attachment & Details below:</p>
                <table border="1" cellpadding="5" cellspacing="0">
                    <tr><th>NAME</th><td>KERNEL_PATCHING for {sheet_name} servers</td></tr>
                    <tr><th>Performed by</th><td>xyz - TEAM</td></tr>
                    <tr><th>Next Communication</th><td>Will be sent before the start of the activity</td></tr>
                    <tr><th>No of Servers</th><td>{len(servers)}</td></tr>
                    <tr><th>Successful Patches</th><td>{successful_patches}</td></tr>
                    <tr><th>Already Patched Servers</th><td>{unique_already_patched_count}</td></tr>
                    <tr><th>Total completed Servers</th><td>{cumulative_patches}</td></tr>
                    <tr><th>Compliance Percentage</th><td>{compliance:.2f}%</td></tr>
                    <tr><th>Contact Details</th><td>example.com;</td></tr>
                </table>
                <p>Thanks & Regards,<br>UNIX Team</p>
            </body>
        </html>
        """

        to_emails, cc_emails = read_email_addresses(EMAIL_FILE)
        attachment_name = f"Kernel_Patching_completed_for_{sheet_name}.xlsx"
        send_email(email_subject, email_body, FROM_EMAIL, to_emails, cc_emails, status_bytes.read(), attachment_name)

        logging.info("Patching process completed successfully.")

except Exception as e:
    logging.error(f"Script execution failed: {str(e)}")

