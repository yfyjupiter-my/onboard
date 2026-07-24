import os
from functools import cached_property

import boto3
from botocore.client import Config
from storages.backends.s3 import S3Storage, clean_name


class MinioMediaStorage(S3Storage):
    """Private MinIO storage. Uploads use the internal endpoint (minio:9000);
    browser GETs are presigned against the PUBLIC host so the signature still
    verifies after nginx proxies /media/ -> MinIO. P1/P2, resolves SEC-001.
    """

    querystring_expire = 900  # 15 min presigned GETs

    @cached_property
    def _public_client(self):
        # Separate client: signs against the public domain the browser actually hits.
        return boto3.client(
            "s3",
            endpoint_url=os.environ["MINIO_PUBLIC_ENDPOINT"],
            aws_access_key_id=os.environ["MINIO_ROOT_USER"],
            aws_secret_access_key=os.environ["MINIO_ROOT_PASSWORD"],
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def url(self, name, parameters=None, expire=None, http_method=None):
        name = self._normalize_name(clean_name(name))
        signed = self._public_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket_name, "Key": name, **(parameters or {})},
            ExpiresIn=self.querystring_expire if expire is None else expire,
            HttpMethod=http_method,
        )
        # Signed path is /<bucket>/<key>; present it as /media/<key>. nginx rewrites
        # /media/ back to /<bucket>/ before MinIO, so the signature still matches.
        # ponytail: str-replace the bucket segment; fixed single bucket, no templating.
        return signed.replace(f"/{self.bucket_name}/", "/media/", 1)
