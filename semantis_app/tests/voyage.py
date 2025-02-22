import voyageai
from dotenv import load_dotenv

load_dotenv()

vo = voyageai.Client()
# This will automatically use the environment variable VOYAGE_API_KEY.
# Alternatively, you can use vo = voyageai.Client(api_key="<your secret key>")

result = vo.embed(["hello world"], model="voyage-law-2")

print(result)