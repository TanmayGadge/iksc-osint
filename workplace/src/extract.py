import os
from typing import Optional, List, Literal
from pydantic import BaseModel, Field
from PIL import Image
from google import genai
from google.genai import types
from dotenv import load_dotenv
import json


load_dotenv()

class ParentDetails(BaseModel):
    name: Optional[str] = Field(default=None, description="Full name of the parent")
    occupation: Optional[str] = Field(default=None, description="Occupation, job, or business of the parent")

class SiblingDetails(BaseModel):
    relation: Optional[str] = Field(default=None, description="Gender title of the sibling (Sister/Brother)")
    marital_status: Literal["married", 'unmarried'] = Field(default='unmarried', description="The marital status of the sibling")

class FamilyDetails(BaseModel):
    father: Optional[ParentDetails] = Field(default=None, description="Father's details")
    mother: Optional[ParentDetails] = Field(default=None, description="Mother's details")
    siblings: Optional[SiblingDetails] = Field(default=None, description="Sibling's details")


class BiodataSchema(BaseModel):
    first_name: Optional[str] = Field(default=None, description="First legal or display name (e.g. Rohan)")
    last_name: Optional[str] = Field(default=None, description="Last legal or display name (e.g. Patil)")
    name: Optional[str] = Field(default=None, description="The full name of the user, created by combining their first name and last name and separated by a space. (e.g. Rohan Patil)")
    date_of_birth: Optional[str] = Field(default=None, description="Date of birth")
    age: Optional[int] = Field(default=None, description="Age in years")
    blood_group: Optional[str] = Field(default=None, description="Blood Group (e.g. O+, A-)")
    weight: Optional[int] = Field(default=None, description="Weight (e.g 70 kg, 154 lb)")
    height: Optional[str] = Field(default=None, description="Height (e.g., 5'10\", 175 cm)")
    complexion: Optional[str] = Field(default=None, description="Complexion or skin tone if mentioned")
    religion: Optional[str] = Field(default=None, description="Religion of the person")
    caste: Optional[str] = Field(default=None, description="Name of the caste if mentioned")
    education: List[str] = Field(default_factory=list, description="Degrees, qualifications, or universities attended")
    occupation: Optional[str] = Field(default=None, description="Job title, designation, or profession")
    employer: Optional[str] = Field(default=None, description="Current employer or company name")
    annual_income: Optional[str] = Field(default=None, description="Salary or annual income")
    hometown: Optional[str] = Field(default=None, description="Native place, village, or hometown")
    address: Optional[str] = Field(default=None, description="Complete address of the person")
    current_city: Optional[str] = Field(default=None, description="Current location or residential city")
    phone_number: Optional[str] = Field(default=None, description="Contact phone or mobile number")
    email: Optional[str] = Field(default=None, description="Email address")
    family_details: Optional[FamilyDetails] = Field(default=None, description="Structured details of father and mother")


def parse_biodata_image(image_path: str, api_key: Optional[str] = None) -> dict:
    """
    Reads a biodata image file and converts its content into structured JSON 
    matching the BiodataSchema using Gemini structured output.
    """
    client = genai.Client(api_key=api_key or os.getenv("GEMINI_API_KEY"))
    
    # Load image using PIL
    image = Image.open(image_path)
    
    prompt = (
        "If the text in biodata image is in a language other than english, then first translate it into english."
        "Extract all available personal, educational, professional, and contact information "
        "from this biodata image. Map the extracted values strictly into the structured schema."
    )
    
    response = client.models.generate_content(
        model="gemini-3.5-flash",
        contents=[image, prompt],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=BiodataSchema,
            temperature=0.1,  # Low temperature for precise factual extraction
        ),
    )
    
    
    return json.loads(str(response.text))


if __name__ == "__main__":
    # Ensure GEMINI_API_KEY is set in environment variables
    image_file_path = "./biodata/images/mayur-talele.png"
    
    if os.path.exists(image_file_path):
        json_output = parse_biodata_image(image_file_path)
        print("Extracted JSON Output:\n")
        print(json_output)
        
        first_name = str(json_output['first_name']).lower()
        last_name = str(json_output['last_name']).lower()
        
        with open(f'../json-files/json/{first_name}-{last_name}-biodata.json', 'w', encoding='utf-8') as file:
            json.dump(json_output, file, indent=4)
    else:
        print(f"File not found: {image_file_path}")