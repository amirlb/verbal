#! /bin/sh

# Read the header content
header_content=$(cat assets/header.html)

# Process each HTML file in app/static
for f in app/static/*.html
do
    # Create a temporary file
    temp_file="${f}.tmp"
    
    # Replace everything between <header> and </header> with the header content
    awk -v header="$header_content" '
        /<header>/ {
            print header
            skip = 1
            next
        }
        /<\/header>/ {
            skip = 0
            next
        }
        !skip {
            print
        }
    ' "$f" > "$temp_file"
    
    # Move the temporary file back to the original
    mv "$temp_file" "$f"
done