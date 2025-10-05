import sys
from utils import ArgoMetadataExtractor

# 1. Initialize the extractor
extractor = ArgoMetadataExtractor()

# 2. Fetch a fresh list of all floats from the ARGO server
print("Fetching the global list of ARGO floats...")
float_list = extractor.get_float_list()

# 3. Get the start and end indices from the command-line arguments
start_index = int(sys.argv[1])
end_index = int(sys.argv[2])

# 4. Define the output file path based on the indices
output_file = f"data/parts/metadata_{start_index}-{end_index-1}.parquet"

# 5. Run the extraction process for the specified slice of floats
print(f"Processing floats from index {start_index} to {end_index-1}...")
extractor.extract_multiple_floats(float_list[start_index:end_index], output_file)

print(f"Extraction complete. Data saved to {output_file}")