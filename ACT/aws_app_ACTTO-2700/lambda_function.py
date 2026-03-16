import boto3
import datetime

ec2 = boto3.client('ec2')
cloudtrail = boto3.client('cloudtrail')

# Explicitly list packer identities for clarity
PACKER_IDENTITIES = ["packer", "packer-role", "packer-ci"]

def lambda_handler(event, context):
    now = datetime.datetime.utcnow()
    instances_to_terminate = []
    volumes_to_delete = []
    keypairs_to_delete = set()

    # Query instances with BOTH key-name and tag:Name starting with 'packer'
    reservations = ec2.describe_instances(
        Filters=[
            {'Name': 'key-name', 'Values': ['packer*']},
            {'Name': 'tag:Name', 'Values': ['packer*', 'Packer*']},
            {'Name': 'instance-state-name', 'Values': ['running', 'stopped']}
        ]
    )['Reservations']

    for reservation in reservations:
        for instance in reservation['Instances']:
            instance_id = instance['InstanceId']
            launch_time = instance['LaunchTime'].replace(tzinfo=None)
            age = now - launch_time
            state = instance['State']['Name']

            print(f"Checking instance {instance_id} | State: {state} | Age: {age}")

            if age.total_seconds() > 100:  # older than 1 hour
                terminate_this_instance = False
                delete_keypair_for_instance = False

                if state == 'running':
                    print(f"Instance {instance_id} running >1h, terminating.")
                    terminate_this_instance = True
                    delete_keypair_for_instance = True

                elif state == 'stopped':
                    # Look up CloudTrail events for this instance in the last 24h
                    events = cloudtrail.lookup_events(
                        LookupAttributes=[
                            {'AttributeKey': 'ResourceName', 'AttributeValue': instance_id}
                        ],
                        StartTime=now - datetime.timedelta(days=1),
                        EndTime=now,
                        MaxResults=10
                    )['Events']

                    # Sort by event time (latest first)
                    events_sorted = sorted(events, key=lambda e: e['EventTime'], reverse=True)

                    stopped_by_packer = False
                    for ev in events_sorted:
                        if ev['EventName'] == 'StopInstances':
                            user_identity = ev.get('Username', '')
                            print(f"Stop event for {instance_id}: {user_identity} at {ev['EventTime']}")
                            if any(p in user_identity.lower() for p in PACKER_IDENTITIES):
                                stopped_by_packer = True
                            break  # only consider the most recent StopInstances event

                    if stopped_by_packer:
                        print(f"Instance {instance_id} stopped by packer, terminating.")
                        terminate_this_instance = True
                        delete_keypair_for_instance = True
                    else:
                        print(f"Instance {instance_id} stopped by another user, keeping.")

                if terminate_this_instance:
                    instances_to_terminate.append(instance_id)

                    # Collect attached volumes
                    for mapping in instance.get('BlockDeviceMappings', []):
                        if 'Ebs' in mapping:
                            volumes_to_delete.append(mapping['Ebs']['VolumeId'])

                    # Collect the keypair only if we decided to delete it
                    if delete_keypair_for_instance and 'KeyName' in instance and instance['KeyName'].lower().startswith('packer'):
                        keypairs_to_delete.add(instance['KeyName'])

    # Terminate instances
    if instances_to_terminate:
        print(f"Terminating: {instances_to_terminate}")
        ec2.terminate_instances(InstanceIds=list(set(instances_to_terminate)))

    # Delete volumes
    for vol_id in set(volumes_to_delete):
        try:
            print(f"Deleting volume: {vol_id}")
            ec2.delete_volume(VolumeId=vol_id)
        except Exception as e:
            print(f"Could not delete volume {vol_id}: {e}")

    # Delete keypairs used by terminated instances (only packer-stopped or running)
    for kp in keypairs_to_delete:
        try:
            print(f"Deleting keypair: {kp}")
            ec2.delete_key_pair(KeyName=kp)
        except Exception as e:
            print(f"Could not delete keypair {kp}: {e}")

    return {
        'terminated_instances': instances_to_terminate,
        'deleted_volumes': volumes_to_delete,
        'deleted_keypairs': list(keypairs_to_delete)
    }
