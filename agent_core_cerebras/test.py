from dotenv import load_dotenv
load_dotenv()

from cerebras.cloud.sdk import Cerebras
client = Cerebras()
models = client.models.list()
print(models)