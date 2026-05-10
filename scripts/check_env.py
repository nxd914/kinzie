from dotenv import load_dotenv

from strategies.crypto.core.config import Config

load_dotenv()

config = Config.from_env()
print("Microstructure ingestion config:")
print(f"  symbols: {','.join(config.symbols)}")
print(f"  depth: {config.book_depth}")
print(f"  persist_jsonl: {config.persist_jsonl}")
print(f"  output_dir: {config.jsonl_output_dir}")
