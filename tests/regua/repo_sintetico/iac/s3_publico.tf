resource "aws_s3_bucket" "dados" {
  bucket = "dados-do-banco"
  acl    = "public-read"
}
