from pydantic import BaseModel, EmailStr, ConfigDict, Field
from datetime import datetime

class UserCreate(BaseModel):
    email : EmailStr
    password : str

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: EmailStr 

class Token(BaseModel):
    access_token: str
    token_type: str

class BoardCreate(BaseModel):
    title: str = Field(min_length=1, max_length=100)
    default_can_edit: bool = True

class BoardOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id :int
    title : str
    join_code : str
    owner_id : int    
    created_at: datetime

class ShareRequest(BaseModel):
    email: EmailStr    

class JoinRequest(BaseModel):
    code : str    