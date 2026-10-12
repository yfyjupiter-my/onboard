import os

import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from django.conf import settings
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Create the MinIO bucket if it does not exist (idempotent). P11."

    def handle(self, *args, **options):
        bucket = os.environ.get("MINIO_BUCKET", "onboard-media")
        client = boto3.client(
            "s3",
            endpoint_url=os.environ["MINIO_ENDPOINT"],
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,  # T7.3: same (scoped) key the app uses
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            config=Config(signature_version="s3v4"),
        )
        try:
            client.head_bucket(Bucket=bucket)
            self.stdout.write(f"bucket '{bucket}' already exists")
        except ClientError as err:
            # Only a missing bucket (404) means "create it"; re-raise 403/etc.
            # so bad creds or transient errors aren't misread as absence. (CODE-002)
            if err.response.get("Error", {}).get("Code") not in ("404", "NoSuchBucket"):
                raise
            client.create_bucket(Bucket=bucket)
            self.stdout.write(self.style.SUCCESS(f"created bucket '{bucket}'"))
