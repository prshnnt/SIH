from utils import ArgoMetadataExtractor

extractor = ArgoMetadataExtractor()
# float_list = extractor.get_float_list()
# extractor.save_float_list(float_list, "float_list.csv")
float_list = extractor.load_float_list("float_list.csv")
import sys
lower_bound =int(sys.argv[1])
upper_bound =int(sys.argv[2])

extractor.extract_multiple_floats(float_list[lower_bound:upper_bound], "data/parts/metadata_error_"+str(lower_bound)+"-"+str(upper_bound)+".parquet")