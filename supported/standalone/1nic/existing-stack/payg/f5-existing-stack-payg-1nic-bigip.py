# Copyright 2021 F5 Networks All rights reserved.
#
# Version 3.14.0

""" Creates Deployment """
COMPUTE_URL_BASE = 'https://www.googleapis.com/compute/v1/'
def FirewallRuleApp(context):
    # Build Application firewall rule
    ports = str(context.properties['applicationPort']).split()
    source_list = str(context.properties['restrictedSrcAddressApp']).split()
    firewallRuleApp = {
        'name': 'appfw-' + context.env['deployment'],
        'type': 'compute.v1.firewall',
        'properties': {
            'network': ''.join([COMPUTE_URL_BASE, 'projects/',
                                context.env['project'], '/global/networks/',
                                 context.properties['mgmtNetwork']]),
            'sourceRanges': source_list,
            'targetTags': ['appfw-'+ context.env['deployment']],
            'allowed': [{
                "IPProtocol": "TCP",
                "ports": ports,
                },
            ]
        }
    }
    return firewallRuleApp

def FirewallRuleMgmt(context):
    # Build Management firewall rule
    source_list = str(context.properties['restrictedSrcAddress']).split()
    firewallRuleMgmt = {
        'name': 'mgmtfw-' + context.env['deployment'],
        'type': 'compute.v1.firewall',
        'properties': {
            'network': ''.join([COMPUTE_URL_BASE, 'projects/',
                                context.env['project'], '/global/networks/',
                                context.properties['mgmtNetwork']]),
            'sourceRanges': source_list,
            'targetTags': ['mgmtfw-'+ context.env['deployment']],
            'allowed': [{
                "IPProtocol": "TCP",
                "ports": [str(context.properties['mgmtGuiPort']),'22'],
                },
            ]
        }
    }
    return firewallRuleMgmt
def Instance(context, mgmtSharedVpc):
    # declare specific instance properties ahead of time as they may change
    network_interfaces = [
            {
                'network': ''.join([COMPUTE_URL_BASE, 'projects/',
                                     mgmtSharedVpc, '/global/networks/',
                                    context.properties['mgmtNetwork']]),
                'subnetwork': ''.join([COMPUTE_URL_BASE, 'projects/',
                                     mgmtSharedVpc, '/regions/',
                                    context.properties['region'], '/subnetworks/',
                                    context.properties['mgmtSubnet']]),
                'accessConfigs': []

            }]

    # access config - conditional on provisionPublicIP parameter (boolean yes/no)
    if str(context.properties['provisionPublicIP']).lower() in ['yes', 'true']:
        network_interfaces[0]['accessConfigs'] = [{
            'name': 'Management NAT',
            'type': 'ONE_TO_ONE_NAT'
        }]
      

    # If not 'DYNAMIC'|'' assume a static address is needed
    mgmtSubnetAddress = context.properties['mgmtSubnetAddress'].upper()
    if mgmtSubnetAddress != "DYNAMIC" and mgmtSubnetAddress != "":
        network_interfaces[0]['networkIP'] = mgmtSubnetAddress
    # Build instance template
    instance = {
        'name': 'bigip1-' + context.env['deployment'],
        'type': 'compute.v1.instance',
        'properties': {
            'canIpForward': True,
            'description': 'F5 BIG-IP configured with 1 interface(s).',
            'hostname': ''.join(['bigip1-', context.env['deployment'], '.c.', context.env['project'], '.internal']),
            'disks': [{
                'deviceName': 'boot',
                'type': 'PERSISTENT',
                'boot': True,
                'autoDelete': True,
                'initializeParams': {
                    'sourceImage': ''.join([COMPUTE_URL_BASE, 'projects/f5-7626-networks-public',
                                            '/global/images/',
                                            context.properties['imageName'],
                                            ])
                }
            }],
            'machineType': 
        ''.join([COMPUTE_URL_BASE, 'projects/',
        context.env['project'], '/zones/',
        context.properties['availabilityZone1'], '/machineTypes/',
        context.properties['instanceType']]),
            'networkInterfaces': network_interfaces,
            'tags': {
              'items': [
                  'mgmtfw-' + context.env['deployment'],
                  'appfw-' + context.env['deployment']
              ]
            },
            'zone': context.properties['availabilityZone1'],
            'metadata': Metadata(context)

        }
    }

    # add no-ip tag if provisionPublicIP = no
    if str(context.properties['provisionPublicIP']).lower() in ['no', 'false']:
        instance['properties']['tags']['items'].append('no-ip')
    return instance

def Metadata(context):

    ALLOWUSAGEANALYTICS = str(context.properties['allowUsageAnalytics']).lower()
    if ALLOWUSAGEANALYTICS == 'yes':
        CUSTHASH = 'CUSTOMERID=`/usr/bin/curl -s "http://metadata.google.internal/computeMetadata/v1/project/numeric-project-id" -H "Metadata-Flavor: Google" |sha512sum|cut -d " " -f 1`;\nDEPLOYMENTID=`/usr/bin/curl -s "http://metadata.google.internal/computeMetadata/v1/instance/id" -H "Metadata-Flavor: Google"|sha512sum|cut -d " " -f 1`;'
        SENDANALYTICS = ' --metrics "cloudName:google,region:' + context.properties['region'] + ',bigipVersion:' + context.properties['imageName'] + ',customerId:${CUSTOMERID},deploymentId:${DEPLOYMENTID},templateName:f5-existing-stack-payg-1nic-bigip.py,templateVersion:3.14.0,licenseType:payg"'
    else:
        CUSTHASH = 'echo "No analytics."'
        SENDANALYTICS = ''

    ## Phone home
    ALLOWPHONEHOME = str(context.properties['allowPhoneHome']).lower()
    if ALLOWPHONEHOME in ['yes', 'true']:
        PHONEHOME = '"tmsh modify sys software update auto-phonehome enabled"'
    else:
        PHONEHOME = '"tmsh modify sys software update auto-phonehome disabled"'

    # Provisioning modules
    PROVISIONING_MODULES = ','.join(context.properties['bigIpModules'].split('-'))

    ntp_servers = str(context.properties['ntpServer']).split()
    ntp_list = ''
    for ntp_server in ntp_servers:
        ntp_list = ntp_list + ' --ntp ' + ntp_server

    timezone = ' --tz UTC'
    if context.properties['timezone']:
       timezone = " --tz {0}".format(str(context.properties['timezone']))

    metadata = {
                'items': [{
                    'key': 'startup-script',
                    'value': ('\n'.join(['#!/bin/bash',
                                    'if [ -f /config/startupFinished ]; then',
                                    '    exit',
                                    'fi',
                                    'if [ ! -f /config/cloud/gce/FIRST_BOOT_COMPLETE ]; then',
                                    'mkdir -p /config/cloud/gce',
                                    'cat <<\'EOF\' > /config/installCloudLibs.sh',
                                    '#!/bin/bash',
                                    'echo about to execute',
                                    'checks=0',
                                    'while [ $checks -lt 120 ]; do echo checking mcpd',
                                    '    tmsh -a show sys mcp-state field-fmt | grep -q running',
                                    '    if [ $? == 0 ]; then',
                                    '        echo mcpd ready',
                                    '        break',
                                    '    fi',
                                    '    echo mcpd not ready yet',
                                    '    let checks=checks+1',
                                    '    sleep 10',
                                    'done',
                                    'echo loading verifyHash script',
                                    'if ! tmsh load sys config merge file /config/verifyHash; then',
                                    '    echo cannot validate signature of /config/verifyHash',
                                    '    exit',
                                    'fi',
                                    'echo loaded verifyHash',
                                    'declare -a filesToVerify=(\"/config/cloud/f5-cloud-libs.tar.gz\" \"/config/cloud/f5-cloud-libs-gce.tar.gz\" \"/var/config/rest/downloads/f5-appsvcs-3.31.0-6.noarch.rpm\")',
                                    'for fileToVerify in \"${filesToVerify[@]}\"',
                                    'do',
                                    '    echo verifying \"$fileToVerify\"',
                                    '    if ! tmsh run cli script verifyHash \"$fileToVerify\"; then',
                                    '        echo \"$fileToVerify\" is not valid',
                                    '        exit 1',
                                    '    fi',
                                    '    echo verified \"$fileToVerify\"',
                                    'done',
                                    'mkdir -p /config/cloud/gce/node_modules/@f5devcentral',
                                    'echo expanding f5-cloud-libs.tar.gz\n',
                                    'tar xvfz /config/cloud/f5-cloud-libs.tar.gz -C /config/cloud/gce/node_modules/@f5devcentral',
                                    'echo expanding f5-cloud-libs-gce.tar.gz',
                                    'tar xvfz /config/cloud/f5-cloud-libs-gce.tar.gz -C /config/cloud/gce/node_modules/@f5devcentral',
                                    'echo cloud libs install complete',
                                    'touch /config/cloud/cloudLibsReady',
                                    'EOF',
                                    'echo \'Y2xpIHNjcmlwdCAvQ29tbW9uL3ZlcmlmeUhhc2ggewpwcm9jIHNjcmlwdDo6cnVuIHt9IHsKICAgICAgICBpZiB7W2NhdGNoIHsKICAgICAgICAgICAgc2V0IGhhc2hlcyhmNS1jbG91ZC1saWJzLnRhci5neikgZThkOTYyZTI5NWE2MDY4NzMxMGI1MGNiZjEwODVjM2JjNjljNzZjMjk0MzljYmNlNjE0MWE1Njc3ZDg5ZmZhZGRlOWFhMWU3MzA4YTg1NDQ4NmFhYmE3OThjZTk4ZTM1YmQyNWZlYjlmY2M2ZDk0MDJhOWI3MmVjODc4NTYzNjEKICAgICAgICAgICAgc2V0IGhhc2hlcyhmNS1jbG91ZC1saWJzLWF3cy50YXIuZ3opIDA5MWVhN2IxOGFjYTdmMThhMGVjMzc3YTY4ODZkNWQ2NjZjYzgxMzQ5ZWFmYTU3MjVhYjA3NThkZGNjMTdjMTBlMDM3MzcxOTUzODRlYWZkNjNjMTE3ZDI1OTEzYzE1YTExMjg0ZDJjYzNiMjIxZDdiYTNjMzE0MjIxNzIxNDJiCiAgICAgICAgICAgIHNldCBoYXNoZXMoZjUtY2xvdWQtbGlicy1henVyZS50YXIuZ3opIGU3OTczYTFmZTg1YjVhODMyYzVlY2QxY2ZjZTY2YjQzYjg0ZTQyY2YyYTA2YjI3NTE3MzRmNzk4MTJkZTE4N2VlMWFkODczMGExMjljYjA4MTk4YTQ1MjE1N2M0NjZiYjg3MTgwYzE3ZGZkMmUwOWI0OWJlNmVmZTllOWE1N2ZlCiAgICAgICAgICAgIHNldCBoYXNoZXMoZjUtY2xvdWQtbGlicy1nY2UudGFyLmd6KSBjZDk1YTVjYzM2YzM5ZjgwZjk1NDc2YWQwMDBmN2RjYzIxYTlmZWY0MTRjOGVkYWM4MmJlMmU0OTFjMGZhOWViYTUxYjE0NWY3NWJhMGYzYzBkYWU0OGUxYzczMTQzMjIxN2IzYmI3MDBmNzFmZTE5MTIxNTJkYmU0MzllODk2NwogICAgICAgICAgICBzZXQgaGFzaGVzKGY1LWNsb3VkLWxpYnMtb3BlbnN0YWNrLnRhci5neikgNWM4M2ZlNmE5M2E2ZmNlYjVhMmU4NDM3YjVlZDhjYzlmYWY0YzE2MjFiZmM5ZTZhMDc3OWY2YzIxMzdiNDVlYWI4YWUwZTdlZDc0NWM4Y2Y4MjFiOTM3MTI0NWNhMjk3NDljYTBiN2U1NjYzOTQ5ZDc3NDk2Yjg3MjhmNGIwZjkKICAgICAgICAgICAgc2V0IGhhc2hlcyhmNS1jbG91ZC1saWJzLWNvbnN1bC50YXIuZ3opIGEzMmFhYjM5NzA3M2RmOTJjYmJiYTUwNjdlNTgyM2U5YjVmYWZjYTg2MmEyNThiNjBiNmI0MGFhMDk3NWMzOTg5ZDFlMTEwZjcwNjE3N2IyZmZiZTRkZGU2NTMwNWEyNjBhNTg1NjU5NGNlN2FkNGVmMGM0N2I2OTRhZTRhNTEzCiAgICAgICAgICAgIHNldCBoYXNoZXMoYXNtLXBvbGljeS1saW51eC50YXIuZ3opIDYzYjVjMmE1MWNhMDljNDNiZDg5YWYzNzczYmJhYjg3YzcxYTZlN2Y2YWQ5NDEwYjIyOWI0ZTBhMWM0ODNkNDZmMWE5ZmZmMzlkOTk0NDA0MWIwMmVlOTI2MDcyNDAyNzQxNGRlNTkyZTk5ZjRjMjQ3NTQxNTMyM2UxOGE3MmUwCiAgICAgICAgICAgIHNldCBoYXNoZXMoZjUuaHR0cC52MS4yLjByYzQudG1wbCkgNDdjMTlhODNlYmZjN2JkMWU5ZTljMzVmMzQyNDk0NWVmODY5NGFhNDM3ZWVkZDE3YjZhMzg3Nzg4ZDRkYjEzOTZmZWZlNDQ1MTk5YjQ5NzA2NGQ3Njk2N2IwZDUwMjM4MTU0MTkwY2EwYmQ3Mzk0MTI5OGZjMjU3ZGY0ZGMwMzQKICAgICAgICAgICAgc2V0IGhhc2hlcyhmNS5odHRwLnYxLjIuMHJjNi50bXBsKSA4MTFiMTRiZmZhYWI1ZWQwMzY1ZjAxMDZiYjVjZTVlNGVjMjIzODU2NTVlYTNhYzA0ZGUyYTM5YmQ5OTQ0ZjUxZTM3MTQ2MTlkYWU3Y2E0MzY2MmM5NTZiNTIxMjIyODg1OGYwNTkyNjcyYTI1NzlkNGE4Nzc2OTE4NmUyY2JmZQogICAgICAgICAgICBzZXQgaGFzaGVzKGY1Lmh0dHAudjEuMi4wcmM3LnRtcGwpIDIxZjQxMzM0MmU5YTdhMjgxYTBmMGUxMzAxZTc0NWFhODZhZjIxYTY5N2QyZTZmZGMyMWRkMjc5NzM0OTM2NjMxZTkyZjM0YmYxYzJkMjUwNGMyMDFmNTZjY2Q3NWM1YzEzYmFhMmZlNzY1MzIxMzY4OWVjM2M5ZTI3ZGZmNzdkCiAgICAgICAgICAgIHNldCBoYXNoZXMoZjUuYXdzX2FkdmFuY2VkX2hhLnYxLjMuMHJjMS50bXBsKSA5ZTU1MTQ5YzAxMGMxZDM5NWFiZGFlM2MzZDJjYjgzZWMxM2QzMWVkMzk0MjQ2OTVlODg2ODBjZjNlZDVhMDEzZDYyNmIzMjY3MTFkM2Q0MGVmMmRmNDZiNzJkNDE0YjRjYjhlNGY0NDVlYTA3MzhkY2JkMjVjNGM4NDNhYzM5ZAogICAgICAgICAgICBzZXQgaGFzaGVzKGY1LmF3c19hZHZhbmNlZF9oYS52MS40LjByYzEudG1wbCkgZGUwNjg0NTUyNTc0MTJhOTQ5ZjFlYWRjY2FlZTg1MDYzNDdlMDRmZDY5YmZiNjQ1MDAxYjc2ZjIwMDEyNzY2OGU0YTA2YmUyYmJiOTRlMTBmZWZjMjE1Y2ZjMzY2NWIwNzk0NWU2ZDczM2NiZTFhNGZhMWI4OGU4ODE1OTAzOTYKICAgICAgICAgICAgc2V0IGhhc2hlcyhmNS5hd3NfYWR2YW5jZWRfaGEudjEuNC4wcmMyLnRtcGwpIDZhYjBiZmZjNDI2ZGY3ZDMxOTEzZjlhNDc0YjFhMDc4NjA0MzVlMzY2YjA3ZDc3YjMyMDY0YWNmYjI5NTJjMWYyMDdiZWFlZDc3MDEzYTE1ZTQ0ZDgwZDc0ZjMyNTNlN2NmOWZiYmUxMmE5MGVjNzEyOGRlNmZhY2QwOTdkNjhmCiAgICAgICAgICAgIHNldCBoYXNoZXMoZjUuYXdzX2FkdmFuY2VkX2hhLnYxLjQuMHJjMy50bXBsKSAyZjIzMzliNGJjM2EyM2M5Y2ZkNDJhYWUyYTZkZTM5YmEwNjU4MzY2ZjI1OTg1ZGUyZWE1MzQxMGE3NDVmMGYxOGVlZGM0OTFiMjBmNGE4ZGJhOGRiNDg5NzAwOTZlMmVmZGNhN2I4ZWZmZmExYTgzYTc4ZTVhYWRmMjE4YjEzNAogICAgICAgICAgICBzZXQgaGFzaGVzKGY1LmF3c19hZHZhbmNlZF9oYS52MS40LjByYzQudG1wbCkgMjQxOGFjOGIxZjE4ODRjNWMwOTZjYmFjNmE5NGQ0MDU5YWFhZjA1OTI3YTZhNDUwOGZkMWYyNWI4Y2M2MDc3NDk4ODM5ZmJkZGE4MTc2ZDJjZjJkMjc0YTI3ZTZhMWRhZTJhMWUzYTBhOTk5MWJjNjVmYzc0ZmMwZDAyY2U5NjMKICAgICAgICAgICAgc2V0IGhhc2hlcyhmNS5hd3NfYWR2YW5jZWRfaGEudjEuNC4wcmM1LnRtcGwpIDVlNTgyMTg3YWUxYTYzMjNlMDk1ZDQxZWRkZDQxMTUxZDZiZDM4ZWI4M2M2MzQ0MTBkNDUyN2EzZDBlMjQ2YThmYzYyNjg1YWIwODQ5ZGUyYWRlNjJiMDI3NWY1MTI2NGQyZGVhY2NiYzE2Yjc3MzQxN2Y4NDdhNGExZWE5YmM0CiAgICAgICAgICAgIHNldCBoYXNoZXMoYXNtLXBvbGljeS50YXIuZ3opIDJkMzllYzYwZDAwNmQwNWQ4YTE1NjdhMWQ4YWFlNzIyNDE5ZThiMDYyYWQ3N2Q2ZDlhMzE2NTI5NzFlNWU2N2JjNDA0M2Q4MTY3MWJhMmE4YjEyZGQyMjllYTQ2ZDIwNTE0NGY3NTM3NGVkNGNhZTU4Y2VmYThmOWFiNjUzM2U2CiAgICAgICAgICAgIHNldCBoYXNoZXMoZGVwbG95X3dhZi5zaCkgMWEzYTNjNjI3NGFiMDhhN2RjMmNiNzNhZWRjOGQyYjJhMjNjZDllMGViMDZhMmUxNTM0YjM2MzJmMjUwZjFkODk3MDU2ZjIxOWQ1YjM1ZDNlZWQxMjA3MDI2ZTg5OTg5Zjc1NDg0MGZkOTI5NjljNTE1YWU0ZDgyOTIxNGZiNzQKICAgICAgICAgICAgc2V0IGhhc2hlcyhmNS5wb2xpY3lfY3JlYXRvci50bXBsKSAwNjUzOWUwOGQxMTVlZmFmZTU1YWE1MDdlY2I0ZTQ0M2U4M2JkYjFmNTgyNWE5NTE0OTU0ZWY2Y2E1NmQyNDBlZDAwYzdiNWQ2N2JkOGY2N2I4MTVlZTlkZDQ2NDUxOTg0NzAxZDA1OGM4OWRhZTI0MzRjODk3MTVkMzc1YTYyMAogICAgICAgICAgICBzZXQgaGFzaGVzKGY1LnNlcnZpY2VfZGlzY292ZXJ5LnRtcGwpIDQ4MTFhOTUzNzJkMWRiZGJiNGY2MmY4YmNjNDhkNGJjOTE5ZmE0OTJjZGEwMTJjODFlM2EyZmU2M2Q3OTY2Y2MzNmJhODY3N2VkMDQ5YTgxNGE5MzA0NzMyMzRmMzAwZDNmOGJjZWQyYjBkYjYzMTc2ZDUyYWM5OTY0MGNlODFiCiAgICAgICAgICAgIHNldCBoYXNoZXMoZjUuY2xvdWRfbG9nZ2VyLnYxLjAuMC50bXBsKSA2NGEwZWQzYjVlMzJhMDM3YmE0ZTcxZDQ2MDM4NWZlOGI1ZTFhZWNjMjdkYzBlODUxNGI1MTE4NjM5NTJlNDE5YTg5ZjRhMmE0MzMyNmFiYjU0M2JiYTliYzM0Mzc2YWZhMTE0Y2VkYTk1MGQyYzNiZDA4ZGFiNzM1ZmY1YWQyMAogICAgICAgICAgICBzZXQgaGFzaGVzKGY1LWFwcHN2Y3MtMy41LjEtNS5ub2FyY2gucnBtKSBiYTcxYzZlMWM1MmQwYzcwNzdjZGIyNWE1ODcwOWI4ZmI3YzM3YjM0NDE4YTgzMzhiYmY2NzY2ODMzOTY3NmQyMDhjMWE0ZmVmNGU1NDcwYzE1MmFhYzg0MDIwYjRjY2I4MDc0Y2UzODdkZTI0YmUzMzk3MTEyNTZjMGZhNzhjOAogICAgICAgICAgICBzZXQgaGFzaGVzKGY1LWFwcHN2Y3MtMy4xOC4wLTQubm9hcmNoLnJwbSkgZTcyZWU4MDA1YTI3MDcwYWMzOTlhYjA5N2U4YWE1MDdhNzJhYWU0NzIxZDc0OTE1ODljZmViODIxZGIzZWY4NmNiYzk3OWU3OTZhYjMxOWVjNzI3YmI1MTQwMGNjZGE4MTNjNGI5ZWI0YTZiM2QxMjIwYTM5NmI1ODJmOGY0MDAKICAgICAgICAgICAgc2V0IGhhc2hlcyhmNS1hcHBzdmNzLTMuMjAuMC0zLm5vYXJjaC5ycG0pIGQ0YmJhODg5MmEyMDY4YmI1M2Y4OGM2MDkwZGM2NWYxNzcwN2FiY2EzNWE3ZWQyZmZmMzk5ODAwNTdmZTdmN2EyZWJmNzEwYWIyMjg0YTFkODNkNzBiNzc0NmJlYWJhZDlkZjYwMzAxN2MwZmQ4NzI4Zjc0NTc2NjFjOTVhYzhkCiAgICAgICAgICAgIHNldCBoYXNoZXMoZjUtYXBwc3Zjcy0zLjI1LjAtMy5ub2FyY2gucnBtKSAyNmYxOWJkYWFhODFjYmUwNDIxYjNlMDhjMDk5ODdmOWRkMGM1NGIwNWE2MjZkNmEyMWE4MzZiMzQyNDhkMmQ5ZDgzMDk1ZjBkYWFkOGU3YTRhMDY4ZTllZjk5Yjg5ZmJjZDI0NmFlOGI2MTdhYzJiMjQ1NjU5OTE1N2QwZThiMwogICAgICAgICAgICBzZXQgaGFzaGVzKGY1LWFwcHN2Y3MtMy4yNi4xLTEubm9hcmNoLnJwbSkgYjQ2MGUxMTY3OWQzOGE5NjU0OWI1MDQxZGVmMjdiNDE5ZjFhNDFjOGY3ODhmOWY4YzdhMDM0YWE1Y2I1YThjOWZkMTUxYzdjNDM5YmViZDA5M2ZjZDg1Y2Q4NjU3ZjFjMDY0NTUxZDkzMzc1NjZmOWZjN2U5NTA2YzU1ZGMwMmMKICAgICAgICAgICAgc2V0IGhhc2hlcyhmNS1hcHBzdmNzLTMuMzEuMC02Lm5vYXJjaC5ycG0pIDY1MDZmZGU1ZDFjMmUwNjc2NjJiNTEzMzg3ZGNjZGEwMjgxZDNiYmM2MDRmYzZkY2Y4ZTU3NDBhZTU2Mzc0ODg5OWY3ZjMzNWUzNDkwMDZmZTNmMGU3NTFjZDcwZDRlZjhiZTM3MDFhZTQ1ZGNhMzA1ZGU2NDlmMjU5ZjA5MGE5CiAgICAgICAgICAgIHNldCBoYXNoZXMoZjUtY2xvdWQtZmFpbG92ZXItMS4xLjAtMC5ub2FyY2gucnBtKSAxNWE0NDBjMjk5ZjllNGFmODZhM2QwZjViMGQ3NWIwMDU0Mzg1Yjk1ZTQ3YzNlZjExNmQyZTBiZmIwMDQxYTI2ZGNiZjU0OTAyOGUyYTI2ZDJjNzE4ZWM2MTQ0NmJkNjU3YmUzOGZiYmNkOWRiNzgxZWZlNTQxNGMxNzRhYzY4YwogICAgICAgICAgICBzZXQgaGFzaGVzKGY1LWNsb3VkLWZhaWxvdmVyLTEuMy4wLTAubm9hcmNoLnJwbSkgMTk2ODFlYjMzZDlmOTEwYzkxM2Y4MTgwMTk5NDg1ZWI2NTNiNGI1ZWJlYWFlMGI5MGE2Y2U4MzQxZDdhMjJmZWQ4ZDIxODE1YjViYTE0OGM0Njg4NTJkMjBjYzI2ZmFkNGM0MjQyZTUwZWNjMTg0ZjFmODc3MGRhY2NlZDZmNmEKICAgICAgICAgICAgc2V0IGhhc2hlcyhmNS1jbG91ZC1mYWlsb3Zlci0xLjQuMC0wLm5vYXJjaC5ycG0pIDQ5ZTkxMDhhMDcwZTBjODcxM2FlYjdiMzMwNjYyMzU4NTQyZTYxYjdjNTNhOWQ0NTEwOGQzN2E5YmY1MjQ2ZjllNGFhYWUxMGNjNjEwNjQ4MDFkY2NjZDIwYmZkNTEwODM0N2IwZjY5NDUxMGU3ZWNlMDdmOTZjNDViYTY4M2IwCiAgICAgICAgICAgIHNldCBoYXNoZXMoZjUtY2xvdWQtZmFpbG92ZXItMS41LjAtMC5ub2FyY2gucnBtKSAzM2E3ZTJkMDQ3MTA2YmNjZTY4MTc1N2E2NTI0MGJmYWNlZGQ0OGUxMzU2N2UwNWZkYjIzYTRiMjY5ZDI2NmFhNTAwMWY4MTE1OGMzOTY0ZGMyOTdmMDQyOGRiMzFjOWRmNDI4MDAyODk4ZDE5MDI4NWIzNDljNTk0MjJhNTczYgogICAgICAgICAgICBzZXQgaGFzaGVzKGY1LWNsb3VkLWZhaWxvdmVyLTEuNi4xLTEubm9hcmNoLnJwbSkgYzFiODQyZGEyMWI4ZDFiYTIxYjZlYjYzYzg1OThhOWVhOTk4NmQ1ZGFkZGMyMWU0ZDI4MGUxZDZiMDlkM2RiMWRlOGFjN2RlNWM4NGVkZjA3YjQzZTRhZjAzZGFmOGZlNzQ3YTQwNDhmNjU3M2Q5NTUyMDYzNTJjZGUyY2VjNjUKICAgICAgICAgICAgc2V0IGhhc2hlcyhmNS1jbG91ZC1mYWlsb3Zlci0xLjcuMS0xLm5vYXJjaC5ycG0pIDE0ZmYwY2QyYmI0OTc4MGNjMGFlMzAyMWM0ZmM4ZmNjMDk2ZTNmY2UyMjU4MDk2YTRhYTAyNmQ2ZDM3ZGU3MjhjYTczNDViZmUzYTc5MDMxZTMzNmU3NGQyNWEyYjQwZmYyODMyNGMyYzc1MmJmMGVlNzFiN2ZjODliNmZjOGZlCiAgICAgICAgICAgIHNldCBoYXNoZXMoZjUtY2xvdWQtZmFpbG92ZXItMS44LjAtMC5ub2FyY2gucnBtKSAyMzA4NmQxY2JmM2NiMjRlYWM3ZWJhMjMwNTE1NmM2MDBmYTIxZjFiODk2MzIxYTJmYTUyMjVkMzMxZDdlNDE0NzFlZGIzZjUzNjgxNDRkODY4NDhhNDUyMGIxZTAwNWMwMTQ0ODVmZjQ1MWU3ZGE2NDI5MDUzZjU4YmZlOGNlNAogICAgICAgICAgICBzZXQgaGFzaGVzKGY1LWNsb3VkLWZhaWxvdmVyLTEuOS4wLTAubm9hcmNoLnJwbSkgMDljMTUzNzczODlhYzE4MzEzMzcwNjM1ZmI5OWY5YWZmMDU5NzA4MDdjYzYwYmZmMDc0ZjgwZjY2NDAyM2NmYzBkOWY1YjdmMmVkN2E4Zjg3OWRlYjJkYTg0YTAzNGJiOWZhOWY0ZTk1Zjk4MDZkNjQ0YWY1MThkYjMyZjE0MjUKCiAgICAgICAgICAgIHNldCBmaWxlX3BhdGggW2xpbmRleCAkdG1zaDo6YXJndiAxXQogICAgICAgICAgICBzZXQgZmlsZV9uYW1lIFtmaWxlIHRhaWwgJGZpbGVfcGF0aF0KCiAgICAgICAgICAgIGlmIHshW2luZm8gZXhpc3RzIGhhc2hlcygkZmlsZV9uYW1lKV19IHsKICAgICAgICAgICAgICAgIHRtc2g6OmxvZyBlcnIgIk5vIGhhc2ggZm91bmQgZm9yICRmaWxlX25hbWUiCiAgICAgICAgICAgICAgICBleGl0IDEKICAgICAgICAgICAgfQoKICAgICAgICAgICAgc2V0IGV4cGVjdGVkX2hhc2ggJGhhc2hlcygkZmlsZV9uYW1lKQogICAgICAgICAgICBzZXQgY29tcHV0ZWRfaGFzaCBbbGluZGV4IFtleGVjIC91c3IvYmluL29wZW5zc2wgZGdzdCAtciAtc2hhNTEyICRmaWxlX3BhdGhdIDBdCiAgICAgICAgICAgIGlmIHsgJGV4cGVjdGVkX2hhc2ggZXEgJGNvbXB1dGVkX2hhc2ggfSB7CiAgICAgICAgICAgICAgICBleGl0IDAKICAgICAgICAgICAgfQogICAgICAgICAgICB0bXNoOjpsb2cgZXJyICJIYXNoIGRvZXMgbm90IG1hdGNoIGZvciAkZmlsZV9wYXRoIgogICAgICAgICAgICBleGl0IDEKICAgICAgICB9XX0gewogICAgICAgICAgICB0bXNoOjpsb2cgZXJyIHtVbmV4cGVjdGVkIGVycm9yIGluIHZlcmlmeUhhc2h9CiAgICAgICAgICAgIGV4aXQgMQogICAgICAgIH0KICAgIH0KICAgIHNjcmlwdC1zaWduYXR1cmUgaWpMY1dkbHdpNG5mdklINC9qUEZKMVk5WGtvZEtWZHVxN0VGV2plV2sweHdmTjVyVkxrQnNodVJPRkpOdG9uV2w1dXYyS1pHMFNUVDhHY0UvRGk5NnVoNlVWakRKQzBnSHdIcUVGa2pkTzNVRXFQd28wOVJRM2xsaVdyb0YzeGFrazlWUTlSdFNBSCtYUXJGNTlNbUFVRGtTT3llVC9DdUY3QXBKNFdFcmNiWnJzeGlhM1RpUkdCZFVXbXowL1hDZlc0L2ZhRUJHVEFUNkFOdzBhTFZxd2tjZ2pxWS9Ld01xWFlITE5VdmtRYm9KQmZtWVVOQXVnM1ozMjlqN1FTZENCbG9wQk9kcG1aM1JxNURPQm15OXpRd2Ewd205MTF6WDEySUpsaUdGUUwwYW1UTSt3ZTFoSENXRFd0ZDVpQ05rd2lldGtzQlhSNkozMWVpZ0M1U2dBPT0KICAgIHNpZ25pbmcta2V5IC9Db21tb24vZjUtaXJ1bGUKfQ==\' | base64 -d > /config/verifyHash',
                                    'cat <<\'EOF\' > /config/waitThenRun.sh',
                                    '#!/bin/bash',
                                    'while true; do echo \"waiting for cloud libs install to complete\"',
                                    '    if [ -f /config/cloud/cloudLibsReady ]; then',
                                    '        echo "Running f5-cloud-libs Version:"',
                                    '        f5-rest-node /config/cloud/gce/node_modules/@f5devcentral/f5-cloud-libs/scripts/onboard.js --version',
                                    '        break',
                                    '    else',
                                    '        sleep 10',
                                    '    fi',
                                    'done',
                                    '\"$@\"',
                                    'EOF',
                                    'cat <<\'EOF\' > /config/cloud/gce/custom-config.sh',
                                    '#!/bin/bash',
                                    'PROGNAME=$(basename $0)',
                                    'function error_exit {',
                                    'echo \"${PROGNAME}: ${1:-\\\"Unknown Error\\\"}\" 1>&2',
                                    'exit 1',
                                    '}',
                                    'function wait_for_ready {',
                                    '   checks=0',
                                    '   ready_response=""',
                                    '   while [ $checks -lt 120 ] ; do',
                                    '      ready_response=$(/usr/bin/curl -sku admin:$passwd -w "%{http_code}" -X GET  https://localhost:${mgmtGuiPort}/mgmt/shared/appsvcs/info -o /dev/null)',
                                    '      if [[ $ready_response == *200 ]]; then',
                                    '          echo "AS3 is ready"',
                                    '          break',
                                    '      else',
                                    '         echo "AS3" is not ready: $checks, response: $ready_response',
                                    '         let checks=checks+1',
                                    '         if [[ $checks == 60 ]]; then',
                                    '           bigstart restart restnoded',
                                    '         fi',
                                    '         sleep 5',
                                    '      fi',
                                    '   done',
                                    '   if [[ $ready_response != *200 ]]; then',
                                    '      error_exit "$LINENO: AS3 was not installed correctly. Exit."',
                                    '   fi',
                                    '}',
                                    'declare -a tmsh=()',
                                    'date',
                                    'echo \'starting custom-config.sh\'',
                                    'source /usr/lib/bigstart/bigip-ready-functions',
                                    'wait_bigip_ready',
                                    'tmsh+=(',
                                    PHONEHOME,
                                    '"tmsh modify sys management-dhcp sys-mgmt-dhcp-config request-options delete { ntp-servers }"',
                                    '\'tmsh save /sys config\'',
                                    ')',
                                    'for CMD in "${tmsh[@]}"',
                                    'do',
                                    '    if $CMD;then',
                                    '        echo "command $CMD successfully executed."',
                                    '    else',
                                    '        error_exit "$LINENO: An error has occurred while executing $CMD. Aborting!"',
                                    '    fi',
                                    'done',
                                    '    wait_bigip_ready',
                                    '    date',
                                    '    ### START CUSTOM TMSH CONFIGURATION',
                                    '    mgmtGuiPort="' + str(context.properties['mgmtGuiPort']) + '"',
                                    '    passwd=$(f5-rest-node /config/cloud/gce/node_modules/@f5devcentral/f5-cloud-libs/scripts/decryptDataFromFile.js --data-file /config/cloud/gce/.adminPassword)',
                                    '    file_loc="/config/cloud/custom_config"',
                                    '    url_regex="^(https?|file)://[-A-Za-z0-9\+&@#/%?=~_|!:,.;]*[-A-Za-z0-9\+&@#/%=~_|]$"',
                                    '    if [[ ' + str(context.properties['declarationUrl']) + ' =~ $url_regex ]]; then',
                                    '       response_code=$(/usr/bin/curl -sk -w "%{http_code}" ' + str(context.properties['declarationUrl']) + ' -o $file_loc)',
                                    '       if [[ $response_code == 200 ]]; then',
                                    '           echo "Custom config download complete; checking for valid JSON."',
                                    '           cat $file_loc | jq .class',
                                    '           if [[ $? == 0 ]]; then',
                                    '               wait_for_ready',
                                    '               response_code=$(/usr/bin/curl -skvvu admin:$passwd -w "%{http_code}" -X POST -H "Content-Type: application/json" -H "Expect:" https://localhost:${mgmtGuiPort}/mgmt/shared/appsvcs/declare -d @$file_loc -o /dev/null)',
                                    '               if [[ $response_code == *200 || $response_code == *502 ]]; then',
                                    '                   echo "Deployment of custom application succeeded."',
                                    '               else',
                                    '                   echo "Failed to deploy custom application; continuing..."',
                                    '                   echo "Response code: ${response_code}"',
                                    '               fi',
                                    '           else',
                                    '               echo "Custom config was not valid JSON, continuing..."',
                                    '           fi',
                                    '       else',
                                    '           echo "Failed to download custom config; continuing..."',
                                    '           echo "Response code: ${response_code}"',
                                    '       fi',
                                    '    else',
                                    '       echo "Custom config was not a URL, continuing..."',
                                    '    fi',
                                    '### END CUSTOM TMSH CONFIGURATION',
                                    'EOF',
                                    'checks=0',
                                    'while [ $checks -lt 12 ]; do echo checking downloads directory',
                                    '    if [ -d "/var/config/rest/downloads" ]; then',
                                    '        echo downloads directory ready',
                                    '        break',
                                    '    fi',
                                    '    echo downloads directory not ready yet',
                                    '    let checks=checks+1',
                                    '    sleep 10',
                                    'done',
                                    'if [ ! -d "/var/config/rest/downloads" ]; then',
                                    '    mkdir -p /var/config/rest/downloads',
                                    'fi',
                                    '/usr/bin/curl -s -f --retry 20 -o /config/cloud/f5-cloud-libs.tar.gz https://cdn.f5.com/product/cloudsolutions/f5-cloud-libs/v4.26.5/f5-cloud-libs.tar.gz',
                                    '/usr/bin/curl -s -f --retry 20 -o /config/cloud/f5-cloud-libs-gce.tar.gz https://cdn.f5.com/product/cloudsolutions/f5-cloud-libs-gce/v2.9.1/f5-cloud-libs-gce.tar.gz',
                                    '/usr/bin/curl -s -f --retry 20 -o /var/config/rest/downloads/f5-appsvcs-3.31.0-6.noarch.rpm https://cdn.f5.com/product/cloudsolutions/f5-appsvcs-extension/v3.31.0/f5-appsvcs-3.31.0-6.noarch.rpm',
                                    'chmod 755 /config/verifyHash',
                                    'chmod 755 /config/installCloudLibs.sh',
                                    'chmod 755 /config/waitThenRun.sh',
                                    'chmod 755 /config/cloud/gce/custom-config.sh',
                                    'mkdir -p /var/log/cloud/google',
                                    CUSTHASH,
                                    'touch /config/cloud/gce/FIRST_BOOT_COMPLETE',
                                    'nohup /usr/bin/setdb provision.extramb 1000 &>> /var/log/cloud/google/install.log < /dev/null &',
                                    'nohup /usr/bin/setdb restjavad.useextramb true &>> /var/log/cloud/google/install.log < /dev/null &',
                                    'nohup /usr/bin/curl -s -f -u admin: -H "Content-Type: application/json" -d \'{"maxMessageBodySize":134217728}\' -X POST http://localhost:8100/mgmt/shared/server/messaging/settings/8100 | jq . &>> /var/log/cloud/google/install.log < /dev/null &',
                                    'nohup /config/installCloudLibs.sh >> /var/log/cloud/google/install.log < /dev/null &',
                                    'nohup /config/waitThenRun.sh f5-rest-node /config/cloud/gce/node_modules/@f5devcentral/f5-cloud-libs/scripts/onboard.js --host localhost --signal ONBOARD_DONE --port 8443 --ssl-port ' + str(context.properties['mgmtGuiPort']) + ' -o /var/log/cloud/google/onboard.log --log-level ' + str(context.properties['logLevel']) + ' --install-ilx-package file:///var/config/rest/downloads/f5-appsvcs-3.31.0-6.noarch.rpm ' + ntp_list + timezone + ' --modules ' + PROVISIONING_MODULES + SENDANALYTICS + ' >> /var/log/cloud/google/install.log < /dev/null & ',                                    
                                    'nohup /config/waitThenRun.sh f5-rest-node /config/cloud/gce/node_modules/@f5devcentral/f5-cloud-libs/scripts/runScript.js --file /config/cloud/gce/custom-config.sh --cwd /config/cloud/gce -o /var/log/cloud/google/custom-config.log --wait-for ONBOARD_DONE --signal CUSTOM_CONFIG_DONE --log-level ' + str(context.properties['logLevel']) + ' >> /var/log/cloud/google/install.log < /dev/null &',
                                    'touch /config/startupFinished',
                                    'fi'
                                    ])
                            )
                }]
    }
    return metadata

def Outputs(context):
    output_ip_options = {
        'public': '.accessConfigs[0].natIP',
        'private': '.networkIP'
    }
    pub_or_priv = 'public' if str(context.properties['provisionPublicIP']).lower() == 'yes' else 'private'

    outputs = [{
        'name': 'region',
        'value': context.properties['region']
    },
    {
        'name': 'selfLink',
        'value': '$(ref.{}.selfLink)'.format('bigip1-' + context.env['deployment'])
    },
    {
        'name': 'mgmtURL',
        'value': 'https://$(ref.bigip1-' + context.env['deployment'] + '.networkInterfaces[0]' + output_ip_options[pub_or_priv] + '):' + str(context.properties['mgmtGuiPort'])
    },
    {
        'name': 'appTrafficAddress',
        'value': '$(ref.bigip1-' + context.env['deployment'] + '.networkInterfaces[0]' + output_ip_options[pub_or_priv] + ')'
    }]
    return outputs

def GenerateConfig(context):
    ## set variables
    # Set project names for networks
    
    mgmtSharedVpc = context.env['project']
    if str(context.properties['mgmtSharedVpc']).lower() != 'none':
        mgmtSharedVpc = context.properties['mgmtSharedVpc']
    

    # build resources
    resources = [Instance(context, mgmtSharedVpc),]
    
    if mgmtSharedVpc == context.env['project']:
        resources = resources + [FirewallRuleApp(context), FirewallRuleMgmt(context)]
    
    
    outputs = Outputs(context)
    return {'resources': resources, 'outputs': outputs}