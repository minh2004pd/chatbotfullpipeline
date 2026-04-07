# ── DynamoDB table cho session persistence ────────────────────────────────────
resource "aws_dynamodb_table" "sessions" {
  name         = "${var.project_name}_sessions"
  billing_mode = "PAY_PER_REQUEST" # pay per request, không cần provision throughput

  hash_key  = "pk" # format: "{app_name}#{user_id}"
  range_key = "session_id"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "session_id"
    type = "S"
  }

  tags = { Project = var.project_name }
}

# ── DynamoDB table cho meetings + utterances (voice transcription) ──────
resource "aws_dynamodb_table" "meetings" {
  # App config default: "memrag-meetings" => với project_name default "memrag"
  name         = "${var.project_name}-meetings"
  billing_mode = "PAY_PER_REQUEST"

  # Single-table design (see app/repositories/meeting_repo.py)
  hash_key  = "PK"
  range_key = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  tags = { Project = var.project_name }
}
