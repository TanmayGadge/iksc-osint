from typing import List, Optional
from pydantic import BaseModel, Field


class DateInfo(BaseModel):
    month: Optional[str] = None
    year: Optional[int] = None
    text: Optional[str] = None


class BasicInfo(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    headline: Optional[str] = None
    about: Optional[str] = None
    emails: List[str] = Field(default_factory=list)
    phone_numbers: List[str] = Field(default_factory=list)
    profile_picture_url: Optional[str] = None
    cover_picture_url: Optional[str] = None
    verified: bool = False
    open_to_work: bool = False
    is_hiring: bool = False
    is_premium: bool = False
    is_creator: bool = False
    is_influencer: bool = False
    is_memorialized: bool = False


class Location(BaseModel):
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    country_code: Optional[str] = None
    raw_text: Optional[str] = None


class Metrics(BaseModel):
    connections_count: Optional[int] = None
    followers_count: Optional[int] = None


class Industry(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None


class ExperienceItem(BaseModel):
    position: Optional[str] = None
    company_name: Optional[str] = None
    company_id: Optional[str] = None
    company_linkedin_url: Optional[str] = None
    company_logo_url: Optional[str] = None
    employment_type: Optional[str] = None
    workplace_type: Optional[str] = None
    location: Optional[str] = None
    is_current: bool = False
    duration: Optional[str] = None
    description: Optional[str] = None
    skills_used: List[str] = Field(default_factory=list)
    start_date: DateInfo = Field(default_factory=DateInfo)
    end_date: DateInfo = Field(default_factory=DateInfo)


class EducationItem(BaseModel):
    school_name: Optional[str] = None
    school_id: Optional[str] = None
    school_linkedin_url: Optional[str] = None
    school_logo_url: Optional[str] = None
    degree: Optional[str] = None
    field_of_study: Optional[str] = None
    period: Optional[str] = None
    description: Optional[str] = None
    grade_or_gpa: Optional[str] = None
    activities: Optional[str] = None
    start_date: DateInfo = Field(default_factory=DateInfo)
    end_date: DateInfo = Field(default_factory=DateInfo)


class SkillItem(BaseModel):
    name: Optional[str] = None
    endorsement_count: int = 0
    used_in_positions: List[str] = Field(default_factory=list)


class CertificationItem(BaseModel):
    title: Optional[str] = None
    issuing_organization: Optional[str] = None
    issued_date: Optional[str] = None
    expiration_date: Optional[str] = None
    credential_id: Optional[str] = None
    credential_url: Optional[str] = None
    organization_logo_url: Optional[str] = None


class CommentItem(BaseModel):
    comment_text: Optional[str] = None
    like_count: int = 0
    is_liked_by_op: bool = False
    op_reply: Optional[str] = None


class PostEngagement(BaseModel):
    like_count: int = 0
    comment_count: int = 0
    repost_count: int = 0


class PostAndActivityItem(BaseModel):
    post_id: Optional[str] = None
    post_url: Optional[str] = None
    published_at: Optional[str] = None
    text: Optional[str] = None
    media_urls: List[str] = Field(default_factory=list)
    engagement: PostEngagement = Field(default_factory=PostEngagement)
    comments: List[CommentItem] = Field(default_factory=list)


class ProjectItem(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    url: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    associated_with: Optional[str] = None


class RecommendationReceived(BaseModel):
    giver_name: Optional[str] = None
    giver_headline: Optional[str] = None
    giver_linkedin_url: Optional[str] = None
    giver_picture_url: Optional[str] = None
    date_given: Optional[str] = None
    text: Optional[str] = None


class RecommendationGiven(BaseModel):
    recipient_name: Optional[str] = None
    recipient_headline: Optional[str] = None
    recipient_linkedin_url: Optional[str] = None
    recipient_picture_url: Optional[str] = None
    date_given: Optional[str] = None
    text: Optional[str] = None


class Recommendations(BaseModel):
    received: List[RecommendationReceived] = Field(default_factory=list)
    given: List[RecommendationGiven] = Field(default_factory=list)


class LanguageItem(BaseModel):
    language: Optional[str] = None
    proficiency: Optional[str] = None


class HonorAwardItem(BaseModel):
    title: Optional[str] = None
    issuer: Optional[str] = None
    issued_date: Optional[str] = None
    description: Optional[str] = None


class PublicationItem(BaseModel):
    title: Optional[str] = None
    publisher: Optional[str] = None
    published_date: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None


class PatentItem(BaseModel):
    title: Optional[str] = None
    patent_number: Optional[str] = None
    issuer: Optional[str] = None
    issued_date: Optional[str] = None
    url: Optional[str] = None
    description: Optional[str] = None


class VolunteeringItem(BaseModel):
    role: Optional[str] = None
    organization: Optional[str] = None
    cause: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None


class InterestItem(BaseModel):
    category: Optional[str] = None
    title: Optional[str] = None
    subtitle: Optional[str] = None
    follower_count: Optional[int] = None
    linkedin_url: Optional[str] = None


class LinkedInProfile(BaseModel):
    id: Optional[str] = Field(default=None, alias="_id")
    linkedin_profile_id: Optional[str] = None
    public_identifier: Optional[str] = None
    linkedin_url: Optional[str] = None
    basic_info: BasicInfo = Field(default_factory=BasicInfo)
    location: Location = Field(default_factory=Location)
    metrics: Metrics = Field(default_factory=Metrics)
    industry: Industry = Field(default_factory=Industry)
    experience: List[ExperienceItem] = Field(default_factory=list)
    education: List[EducationItem] = Field(default_factory=list)
    skills: List[SkillItem] = Field(default_factory=list)
    certifications: List[CertificationItem] = Field(default_factory=list)
    posts_and_activity: List[PostAndActivityItem] = Field(default_factory=list)
    projects: List[ProjectItem] = Field(default_factory=list)
    recommendations: Recommendations = Field(default_factory=Recommendations)
    languages: List[LanguageItem] = Field(default_factory=list)
    honors_and_awards: List[HonorAwardItem] = Field(default_factory=list)
    publications: List[PublicationItem] = Field(default_factory=list)
    patents: List[PatentItem] = Field(default_factory=list)
    volunteering: List[VolunteeringItem] = Field(default_factory=list)
    interests_and_following: List[InterestItem] = Field(default_factory=list)

    class Config:
        populate_by_name = True