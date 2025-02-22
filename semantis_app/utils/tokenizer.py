import logging
from typing import Dict, List, Tuple
# If not installed yet, run: pip install voyageai
import voyageai
from transformers.tokenization_utils_base import PreTrainedTokenizerBase

from dotenv import load_dotenv

load_dotenv()


logging.basicConfig(level=logging.INFO)

# Explicitly create the Voyage client instance,
# similar to your snippet: vo = voyageai.Client()
vo = voyageai.Client()  # Uses VOYAGE_API_KEY from environment variable unless specified

class VoyageTokenizerWrapper(PreTrainedTokenizerBase):
    """
    Minimal wrapper for Voyage's token-counting API, adapted to Docling's HybridChunker.
    This wrapper uses Voyage's token count to simulate tokens.
    """

    def __init__(
        self,
        model_name: str = "voyage-law-2",
        max_length: int = 8191,
        **kwargs
    ):
        """
        Initialize the tokenizer.

        Args:
            model_name: The name of the Voyage model, e.g. "voyage-3".
            max_length: Max sequence length. Docling uses this to handle chunking.
        """
        super().__init__(model_max_length=max_length, **kwargs)
        
        logging.info("Initializing VoyageTokenizerWrapper...")
        self.model_name = model_name
        self.max_length = max_length
        
        # We'll reuse the global 'vo' object here. 
        # If you need a different key or a separate client, you could pass it in the constructor.
        self.vo = vo

        # Because Voyage doesn't expose a "true" vocabulary or a limit on tokens, we define a fake size:
        self._vocab_size = 100000  # Arbitrary big number

        # Optional quick test to confirm everything works:
        test_count = self.vo.count_tokens(["Hello world"], model=self.model_name)
        logging.info(f"Test token count for 'Hello world': {test_count}")

    def tokenize(self, text: str, **kwargs) -> List[str]:
        """
        Main method used by HybridChunker. 
        We use Voyage to count how many tokens the text *would* have, 
        and return that many placeholder tokens.
        """
        logging.info(f"Tokenizing with Voyage model: '{self.model_name}'")
        logging.info(f"Text to tokenize: {text}")

        # Voyage's count_tokens returns an integer directly
        token_count = self.vo.count_tokens([text], model=self.model_name)
        
        print(f"[Voyage] For text:\n{text}\nToken count = {token_count}\n")

        # Return a placeholder list of token_count strings, e.g. ["0","1","2",...]
        return [str(i) for i in range(token_count)]

    def _tokenize(self, text: str) -> List[str]:
        """
        Internal HuggingFace tokenize call; just delegates to our main tokenize().
        """
        return self.tokenize(text)

    def _convert_token_to_id(self, token: str) -> int:
        """
        Convert our placeholder token string (e.g. "42") to an integer 42.
        """
        return int(token)

    def _convert_id_to_token(self, index: int) -> str:
        """
        Convert an integer ID back to a string placeholder.
        """
        return str(index)

    def get_vocab(self) -> Dict[str, int]:
        """
        Return a dummy vocabulary for HuggingFace compatibility.
        We simply map "0" -> 0, "1" -> 1, etc., up to _vocab_size-1.
        """
        return {str(i): i for i in range(self._vocab_size)}

    @property
    def vocab_size(self) -> int:
        """
        Return the stand-in vocabulary size.
        """
        return self._vocab_size

    def save_vocabulary(self, *args) -> Tuple[str]:
        """
        Stub method to comply with HuggingFace's API. No actual vocab file is saved.
        """
        logging.info("VoyageTokenizerWrapper.save_vocabulary called — no action taken.")
        return ()

    @classmethod
    def from_pretrained(cls, *args, **kwargs):
        """
        Class method to match HuggingFace's interface if needed by external code.
        """
        logging.info("VoyageTokenizerWrapper.from_pretrained called.")
        return cls(*args, **kwargs)


if __name__ == "__main__":
    # Demonstrate usage
    logging.info("Creating a VoyageTokenizerWrapper instance...")
    voyage_tokenizer = VoyageTokenizerWrapper(model_name="voyage-law-2")

    sample_texts = [
        "The Mediterranean diet emphasizes fish, olive oil, and vegetables, believed to reduce chronic diseases.",
        "Photosynthesis in plants converts light energy into glucose and produces essential oxygen."
    ]

    logging.info("Testing tokenization on sample texts...\n")
    for txt in sample_texts:
        token_count = vo.count_tokens([txt], model="voyage-3")
        print(f"Text: {txt}")
        print(f"Token count: {token_count}\n")
