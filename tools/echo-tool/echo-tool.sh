#!/bin/bash
# Simple test tool for Vibelike sandbox integration

# Handle both absolute and relative output paths
OUTPUT_DIR="${OUTPUT_DIR:-.}"
if [[ "$OUTPUT_DIR" == "/workspace"* ]]; then
    # If OUTPUT_DIR starts with /workspace, convert to relative workspace path
    OUTPUT_DIR="$(pwd)${OUTPUT_DIR#/workspace}"
fi

OUTPUT_FILE="$OUTPUT_DIR/output.txt"

# Create output directory
mkdir -p "$OUTPUT_DIR" 2>/dev/null || true

# Echo all arguments to stdout
echo "Echo Tool Execution"
echo "=================="
echo "Arguments: $@"
echo "Working directory: $(pwd)"
echo "Output dir: $OUTPUT_DIR"
echo ""

# Write input arguments to output file (handle permission errors gracefully)
{
    echo "Test Tool Output"
    echo "================"
    echo "Timestamp: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
    echo "Arguments: $@"
    echo "Exit code: 0"
} > "$OUTPUT_FILE" 2>/dev/null || {
    # If output file can't be written, still exit 0
    echo "Warning: Could not write to $OUTPUT_FILE"
}

if [ -f "$OUTPUT_FILE" ]; then
    echo "Output written to: $OUTPUT_FILE"
    cat "$OUTPUT_FILE"
fi

exit 0
