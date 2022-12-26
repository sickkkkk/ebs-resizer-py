**EBS Resizer**
A small cli tool to resize root volume of ebs backed ec2 instance.
Sample usage:

    python ./resizer.py --name my-precious-instance --add 10
Tool is in its infant stages so there are a number of constraints:

 - it uses paramiko library to perform resizing of extended EBS volume on-the go on the instance itself, thus burden of providing key-file falls on user - it has to have the same name as the keypair attached to the instance and must be placed near the script itself
 - to avoid IAM role-based acces shenenigans tool simply feeds remote ssh commands from text file located in the root directory - a good way of improvement is to create an instance profile with s3 and ssm access permissions and store resizing fs bash script in a non-public s3 bucket, executing it via ssm-manager functionality (SSM-RunCommand option)
 - please note AWS service constraints - you cant resize a root volume of a given instance more than one time in a six hours
 - solution is designed only for Ubuntu OS and ext* filesystems but it can be further handled by providing a proper resize bash script or a subset of commands to be fed to ssh client function inside
 - and YEAH! ZERO DOWNTIME!
