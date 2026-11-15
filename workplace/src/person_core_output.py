from typing import List, Literal, Optional
from pydantic import BaseModel, Field


class EducationItem(BaseModel):
    educationLevel: Optional[
        Literal["SSC", "HSC", "Diploma", "Graduation", "Post-Grad", "PhD", "Other"]
    ] = Field(
        default=None,
        description="Education Level. Map Bachelor's to Graduation, Master's to Post-Grad, Doctorate to PhD.",
    )
    institutionSchoolCollege: Optional[str] = Field(
        default=None,
        description="Institution / School / College name extracted from schoolName.",
    )
    boardUniversity: Optional[str] = Field(
        default=None,
        description="Board or University name if distinct from institution, otherwise duplicate schoolName or None.",
    )
    passingYear: Optional[str] = Field(
        default=None,
        description="Passing Year extracted from end date (YYYY format).",
    )
    percentageCGPA: Optional[str] = Field(
        default=None,
        description="Percentage or CGPA if explicitly mentioned in degree description, otherwise None.",
    )


class CurrentJob(BaseModel):
    employmentType: Optional[
        Literal["Full-time", "Part-time", "Freelance", "Contract", "Internship"]
    ] = Field(
        default=None,
        description="Employment Type for the current role.",
    )
    designation: Optional[str] = Field(
        default=None,
        description="Job title / Designation mapped from position.",
    )
    company: Optional[str] = Field(
        default=None,
        description="Company name mapped from companyName.",
    )
    industry: Optional[str] = Field(
        default=None,
        description="Industry name or sector.",
    )
    incomeMonthly: Optional[str] = Field(
        default=None,
        description="Monthly income (set to None unless specified).",
    )
    startDate: Optional[str] = Field(
        default=None,
        description="Start Date formatted as MM/YYYY.",
    )
    endDate: Optional[str] = Field(
        default=None,
        description="End Date (leave as None for current active job).",
    )


class PastJobEntry(BaseModel):
    employmentType: Optional[
        Literal["Full-time", "Part-time", "Freelance", "Contract", "Internship"]
    ] = Field(
        default=None,
        description="Employment Type for the past job role.",
    )
    designation: Optional[str] = Field(
        default=None,
        description="Job title or designation.",
    )
    company: Optional[str] = Field(
        default=None,
        description="Company name.",
    )
    industry: Optional[str] = Field(
        default=None,
        description="Industry name or sector.",
    )
    incomeMonthly: Optional[str] = Field(
        default=None,
        description="Monthly income.",
    )
    startDate: Optional[str] = Field(
        default=None,
        description="Start Date formatted as MM/YYYY.",
    )
    endDate: Optional[str] = Field(
        default=None,
        description="End Date formatted as MM/YYYY.",
    )


class PastJobs(BaseModel):
    notApplicable: Optional[bool] = Field(
        default=None,
        description="Set to True if no past job history exists, otherwise False.",
    )
    entries: Optional[List[PastJobEntry]] = Field(
        default=None,
        description="Array of past job position entries.",
    )


class ForeignTravelEntry(BaseModel):
    purpose: Optional[
        Literal[
            "Work", "Education", "Tourism", "Medical", "Family", "Business", "Other"
        ]
    ] = Field(
        default=None,
        description="Primary purpose of foreign travel.",
    )
    country: Optional[str] = Field(
        default=None,
        description="Country visited.",
    )
    year: Optional[str] = Field(
        default=None,
        description="Year of travel.",
    )
    duration: Optional[str] = Field(
        default=None,
        description="Duration of stay (e.g., '3 months').",
    )


class ForeignTravel(BaseModel):
    notApplicable: Optional[bool] = Field(
        default=None,
        description="Set to True if no foreign travel history exists, otherwise False.",
    )
    entries: Optional[List[ForeignTravelEntry]] = Field(
        default=None,
        description="Array of foreign travel entries.",
    )


class AchievementItem(BaseModel):
    achievementTitle: Optional[str] = Field(
        default=None,
        description="Title of the achievement, certification, or award.",
    )
    year: Optional[str] = Field(
        default=None,
        description="Year awarded or issued.",
    )
    issuedByOrganization: Optional[str] = Field(
        default=None,
        description="Issuing organization or institution.",
    )
    additionalDetails: Optional[str] = Field(
        default=None,
        description="Additional description or context about the achievement.",
    )


class PersonCoreForm(BaseModel):
    educationHistory: Optional[List[EducationItem]] = Field(
        default=None,
        description="List of education history items.",
    )
    currentJob: Optional[CurrentJob] = Field(
        default=None,
        description="Current active job position details where end date is 'Present'.",
    )
    pastJobs: Optional[PastJobs] = Field(
        default=None,
        description="Past job experience container and list of past jobs.",
    )
    foreignTravel: Optional[ForeignTravel] = Field(
        default=None,
        description="Foreign travel history container and entries.",
    )
    hobbiesAndInterests: Optional[List[str]] = Field(
        default=None,
        description="List of hobbies, interests, or personal skills.",
    )
    achievementsAndAwards: Optional[List[AchievementItem]] = Field(
        default=None,
        description="List of achievements, awards, or professional certifications.",
    )