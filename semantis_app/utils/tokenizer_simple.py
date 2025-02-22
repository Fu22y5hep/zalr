import voyageai
from dotenv import load_dotenv

load_dotenv()

vo = voyageai.Client()
# This will automatically use the environment variable VOYAGE_API_KEY.
# Alternatively, you can use vo = voyageai.Client(api_key="<your secret key>")

texts = [ 
    "The Mediterranean diet emphasizes fish, olive oil, and vegetables, believed to reduce chronic diseases.",
    "Photosynthesis in plants converts light energy into glucose and produces essential oxygen."
]

total_tokens = vo.count_tokens(texts, model="voyage-3")
print(total_tokens)