import json
import os
import boto3
from botocore.exceptions import ClientError
from botocore.vendored import requests

COMPANY_JIRA_PREFIX = os.environ['COMPANY_JIRA_PREFIX']
JIRA_API_URI = "https://" + COMPANY_JIRA_PREFIX + ".atlassian.net/rest/api/2/search"
JIRA_TICKETS_URI = "https://" + COMPANY_JIRA_PREFIX + ".atlassian.net/browse/"
SENDER = "Jira Reminder " + os.environ['SENDER_EMAIL_ADDRESS']
CHARSET = "UTF-8"
SUBJECT = "Please update your Jira tickets"
SES_REGION = "us-east-1"


def lambda_handler(event, context):
    jira_assignments = get_jira_assigments()

    for email_address, tickets in jira_assignments.items():
        body_html = generate_email_html(tickets)
        body_text_only = generate_email_text(tickets)
        send_reminder_email(email_address, body_html, body_text_only)


def get_jira_assigments():
    """
        Gets data from Jira API and builds list of tickets by assignee
    """
    username = os.environ['JIRA_USERNAME']
    password = os.environ['JIRA_PASSWORD']

    params = {
        "jql": 'status in ("IN PROGRESS", "CODE REVIEW") AND assignee != Unassigned',
        "startAt": 0,
        "maxResults": 100,
        "fields": [],
        "expand": [],
        "validateQuery": "true"
    }
    headers = {
        'Content-Type': 'application/json',
        'Accept': '*/*'
    }

    assignments = {}
    count = 0

    while True:
        params['startAt'] = count
        response = requests.post(JIRA_API_URI, auth=(username, password), data=json.dumps(params), headers=headers)
        jira_data = response.json()

        for issue in jira_data['issues']:

            ticket = get_ticket_data(issue)

            assignee = issue['fields']['assignee']['emailAddress']

            if assignee not in assignments:
                assignments[assignee] = []

            assignments[assignee].append(ticket)

        count += len(jira_data['issues'])

        if count >= int(jira_data['total']):
            return assignments


def get_ticket_data(issue):
    fields = issue['fields']
    ticket = {}
    ticket['key'] = issue['key']
    ticket['summary'] = fields['summary']
    ticket['status'] = fields['status']['name']

    if fields['timeestimate'] is None:
        ticket['timeestimate'] = 0
    else:
        ticket['timeestimate'] = int(fields['timeestimate']) / 3600

    return ticket


def send_reminder_email(email_address, body_html, body_text_only):
    client = boto3.client('ses', region_name=SES_REGION)

    try:
        response = client.send_email(
            Destination={
                'ToAddresses': [
                    email_address,
                ],
            },
            Message={
                'Body': {
                    'Html': {
                        'Charset': CHARSET,
                        'Data': body_html,
                    },
                    'Text': {
                        'Charset': CHARSET,
                        'Data': body_text_only,
                    },
                },
                'Subject': {
                    'Charset': CHARSET,
                    'Data': SUBJECT,
                },
            },
            Source=SENDER,
        )
    except ClientError as e:
        print(e.response['Error']['Message'])
        raise

    print("Email sent! Message ID:"),
    print(response['MessageId'])


def generate_email_html(tickets):
    body_html = [
        'The following tickets are open or in code review. Please ensure their status and remaining hours are up to date.',
        '<br><br>',
        '<table style="border-spacing: 10px">',
        '<tr><td>Ticket Number</td><td>Status</td><td>Time Remaining</td><td>Description</td></tr>'
    ]

    for ticket in tickets:
        body_html.append('<tr>')
        body_html.append('<td><a href="' + JIRA_TICKETS_URI + '{0}">{0}</a></td>'.format(ticket['key']))
        body_html.append('<td>{0}</td>'.format(ticket['status']))
        body_html.append('<td style="text-align: right">{0} hrs</td>'.format(str(ticket['timeestimate'])))
        body_html.append('<td>{0}</td>'.format(ticket['summary']))
        body_html.append('</tr>')

    body_html.append('</table>')

    body_html = '\n'.join(body_html)

    return body_html


def generate_email_text(tickets):
    body_text_only = """
            The following tickets are open or in code review. Please ensure their status and remaining hours are up to date.
            
            Ticket Number                   Status      Time Remaining      Description
            """

    for ticket in tickets:
        body_text_only += JIRA_TICKETS_URI +'{0}'.format(ticket['key'])
        body_text_only += '     {0}'.format(ticket['status'])
        body_text_only += '     {0} hrs'.format(str(ticket['timeestimate']))
        body_text_only += '     {0}'.format(ticket['summary'])

    return body_text_only
