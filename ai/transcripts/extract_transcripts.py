import os
import json
import glob

def extract_text():
    # Use glob to find all json files
    files = glob.glob('ai/transcripts/transcripts/*.json')
    output_path = 'ai/transcripts/clean_text.txt'
    
    with open(output_path, 'w', encoding='utf-8') as outfile:
        for fpath in files:
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    # The files seem to be double encoded or just contain a string at the start
                    # "{\n \"text\": ...
                    if content.startswith('"') and content.endswith('"'):
                        # It might be a json string, let's try to load it
                        data_str = json.loads(content) 
                        # Now data_str should be the inner json string or object
                        if isinstance(data_str, str):
                            data = json.loads(data_str)
                        else:
                            data = data_str
                    else:
                        data = json.loads(content)
                    
                    text = data.get('text', '')
                    if text:
                        outfile.write(text + "\n\n")
            except Exception as e:
                print(f"Error processing {fpath}: {e}")

    print(f"Extraction complete. Saved to {output_path}")

if __name__ == "__main__":
    extract_text()
