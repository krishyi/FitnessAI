import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    USDA_API_KEY = os.getenv("USDA_API_KEY")
    USDA_BASE_URL = "https://api.nal.usda.gov/fdc/v1/"

    @classmethod
    def validate(cls):
        if not cls.USDA_API_KEY:
            print("Missing USDA_API_KEY — check your .env file")
            exit(1)