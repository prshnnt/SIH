from utils import ArgoMetadataExtractor

extractor: ArgoMetadataExtractor = ArgoMetadataExtractor()
float_list = extractor.get_float_list()

extractor.save_float_list(float_list, "float_list.json")
len(float_list)