"""A basic ebs-resizer tool"""
import os
import sys
import argparse
import time
import boto3
import botocore
import paramiko


def get_ec2_info(nametag):
    """
    Retrieve values from describe_instances method in ec2 client library.
    The result is dictionary
    """
    try:
        response = ec2.describe_instances(
            Filters=[
                {'Name': 'tag:Name',
                'Values': f'{nametag}'
                }
            ]
        )
    except botocore.exceptions.ClientError as client_error:
        print(f"Error Message: {client_error.response['Error']['Message']}")
        print(f"Request ID: {client_error.response['ResponseMetadata']['RequestId']}")
        print(f"Http code: {client_error.response['ResponseMetadata']['HTTPStatusCode']}")
        sys.exit()
    ec2info = dict()
    try:
        ec2_instance = response["Reservations"][0]["Instances"][0]
        ec2info["ec2_instance_id"]=ec2_instance["InstanceId"]
        ec2info["ec2_instance_status"]=ec2_instance['State']['Name']
        ec2info["ec2_root_volumeid"]=ec2_instance["BlockDeviceMappings"][0]['Ebs']['VolumeId']
        ec2info["ec2_root_volume_status"]=ec2_instance["BlockDeviceMappings"][0]['Ebs']['Status']
        ec2info["ec2_public_ip"]=ec2_instance["PublicIpAddress"]
        ec2info["ec2_kp_filename"]=ec2_instance["KeyName"]
    except IndexError:
        sys.exit("Unable to retrieve data. Check instance name")
    source_root_volume_id=ec2info["ec2_root_volumeid"]
    try:
        response = ec2.describe_volumes(
            Filters=[
            {'Name': 'volume-id',
            'Values': f'{source_root_volume_id}'
            }
            ]
        )
    except botocore.exceptions.ClientError as client_error:
        print(f"Error Message: {client_error.response['Error']['Message']}")
        print(f"Request ID: {client_error.response['ResponseMetadata']['RequestId']}")
        print(f"Http code: {client_error.response['ResponseMetadata']['HTTPStatusCode']}")
        sys.exit()
    ec2info["ec2_root_volume_size"]=str(response["Volumes"][0]['Size'])
    return ec2info

def get_volume_modification_state(volume_id):
    """querry ec2 client for volume modification task"""
    try:

        response = ec2.describe_volumes_modifications(
        VolumeIds=[volume_id]
)
    except botocore.exceptions.ClientError as client_error:
        print(f"Error Message: {client_error.response['Error']['Message']}")
        print(f"Request ID: {client_error.response['ResponseMetadata']['RequestId']}")
        print(f"Http code: {client_error.response['ResponseMetadata']['HTTPStatusCode']}")
        sys.exit()
    return response['VolumesModifications'][0]['ModificationState']
def resize_ec2_root_volume(volume_id, new_size):
    """querry ec2 client to do actual resizing of root volume"""
    try:
        ec2.modify_volume(VolumeId=volume_id, Size=new_size, DryRun=False)
    except botocore.exceptions.ClientError as client_error:
        print(f"Error Message: {client_error.response['Error']['Message']}")
        print(f"Request ID: {client_error.response['ResponseMetadata']['RequestId']}")
        print(f"Http code: {client_error.response['ResponseMetadata']['HTTPStatusCode']}")
        sys.exit()
    return True
def push_ec2_ssh_payload(kp_name, ec2_public_ip, payload_cmd, num_retries):
    """
    for development sake assuming we store keytab localy near .py file itself
    probably a better solution would be to put contents of keypair file on to
    a parameter or secrets storage inside AWS itself
    and dump it to a temporary file during script execution -
    but it requires more complex setup and debugging
    looks like a good way of improvement a solution to a prodcution ready state (TBD)"""
    if num_retries >= 10:
        return False
    timeout_span=5
    try:
        keytab_file = paramiko.RSAKey.from_private_key_file(f"./{kp_name}"+".pem")
    except Exception as keytab_error:
        sys.exit(keytab_error)
    try:
        num_retries+=1
        print(f"SSH on to {ec2_public_ip}")
        ssh.connect(hostname=ec2_public_ip, username='ubuntu', pkey=keytab_file)
        stdin, stdout, stderr=ssh.exec_command(bytes(payload_cmd, "utf-8")) # bytes object required
        print("stdin:\n", (stdin.read()).decode(encoding="UTF-8")) # get a fancy output
        print("stdout:\n", (stdout.read()).decode(encoding="UTF-8")) # get a fancy output
        print('stderr:\n', (stderr.read()).decode(encoding="UTF-8")) # get a fancy output
        return True
    except Exception as ssh_client_error:
        print(ssh_client_error)
        time.sleep(timeout_span)
        print(f"RE-trying to SSH on to {ec2_public_ip}")
        push_ec2_ssh_payload(kp_name, ec2_public_ip, payload_cmd, num_retries)

# Start with defining and validating arguments
parser=argparse.ArgumentParser(description="EC2 Root Volume Resize CLI. \
With ZERO downtime.Specify instance name tag and ammount of data to \
add in gigabytes",
                                formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("--name", required=True, type=str, help="EC2 Instance name")
parser.add_argument("--add", required=True, type=int, help="Disk space to add")
args=parser.parse_args()
config=vars(args)

# Get script working values from config[]
instance_name=config['name']
added_space=config['add']

# add some argument checks
if added_space < 1:
    sys.exit("You cannot add less than 1 gigs to a volume. Exiting...")
# init authentication variables
try:
    aws_key_id=os.environ['AWS_ACCESS_KEY_ID']
    aws_api_key=os.environ['AWS_SECRET_ACCESS_KEY']
    region=os.environ["AWS_DEFAULT_REGION"]
except KeyError:
    sys.exit("No auth values provided. Check if credentials are in place\
            \nCheck the refrence at:\
            \nhttps://boto3.amazonaws.com/v1/documentation/api/latest/guide/credentials.html")
# init ec2 client from boto3 library
ec2=boto3.client('ec2',
                aws_access_key_id=aws_key_id,
                aws_secret_access_key=aws_api_key,
                region_name=region)
# init paramiko ssh client
ssh = paramiko.SSHClient()
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
print("Initial parameters:")
ec2_params=get_ec2_info(instance_name)
ssh_kp=ec2_params["ec2_kp_filename"]
ssh_ip=ec2_params["ec2_public_ip"]
root_volume_id=ec2_params["ec2_root_volumeid"]
root_volume_initial_size=ec2_params["ec2_root_volume_size"]
new_root_volume_size=int(root_volume_initial_size)+int(added_space)
try:
    # allocate subset of commands
    payload_cmds=[line.strip() for line in open("ssh_payload.txt","rb")]
except Exception as error:
    print(error)
# create a summary for user
for key,value in ec2_params.items():
    print("\t"+ key +": "+ value)
print(f"You're about to add {added_space} gigs to instance named '{instance_name}'")
input("Press any key to continue...\n")

# proceed to resizing
resize_ec2_root_volume(root_volume_id, new_root_volume_size)
while True:
    state = get_volume_modification_state(root_volume_id)
    if state == "completed" or state is None:
        break
    elif state == "failed":
        sys.exit('Failed to modify volume size')
    else:
        print("Waiting for volume resize task to complete...")
        time.sleep(60)
print("Done and done! Proceed to fs resize task")
for cmd in payload_cmds:
    push_ec2_ssh_payload(ssh_kp, ssh_ip, cmd, 0)
