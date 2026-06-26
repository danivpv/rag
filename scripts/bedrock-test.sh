#!/bin/bash

echo "======================================"
echo " Testing Titan Embeddings v2"
echo "======================================"

aws bedrock-runtime invoke-model \
  --model-id "amazon.titan-embed-text-v2:0" \
  --body fileb://scripts/input/titan_test_body.json \
  --region us-east-1 \
  scripts/output/titan_response.json

echo "Raw Titan Response:"
cat scripts/output/titan_response.json
echo -e "\n\nExtracting embedding size with python:"
uv run python -c "import json; d=json.load(open('scripts/output/titan_response.json', encoding='utf-8')); print(f'Embedding dim: {len(d[\"embedding\"])}')"


echo -e "\n======================================"
echo " Testing Claude 4.5 Haiku"
echo "======================================"

aws bedrock-runtime invoke-model \
  --model-id "us.anthropic.claude-haiku-4-5-20251001-v1:0" \
  --body fileb://scripts/input/claude_test_body.json \
  --region us-east-1 \
  scripts/output/claude_response.json

echo "Raw Claude Response:"
cat scripts/output/claude_response.json
echo -e "\n\nExtracting text with python:"
uv run python -c "import json; d=json.load(open('scripts/output/claude_response.json', encoding='utf-8')); print('Claude says:', d['content'][0]['text'])"

echo -e "\n======================================"
echo " TESTS COMPLETE"
echo "======================================"
