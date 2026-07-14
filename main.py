import os
import base64
import cv2
import traceback
import tempfile
from fastapi import FastAPI, File, UploadFile, Form
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from ultralytics import YOLO
import google.generativeai as genai
from datetime import datetime
import re
from typing import List
import urllib.request
import urllib.parse
import json
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from io import BytesIO
from dotenv import load_dotenv

load_dotenv()

# Initialize FastAPI app
app = FastAPI(title="Lung Disease Detection AI")

# CORS setup
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize AI Chatbot
try:
    api_key = os.getenv("GEMINI_API_KEY", "AIzaSyAXdglZWZ38yMYXa-oH3zUfNpe9BFOGwsY")
    if api_key:
        genai.configure(api_key=api_key)
        chat_model = genai.GenerativeModel('gemini-1.5-flash-latest')
        chat = chat_model.start_chat()
    else:
        chat = None
        print("Warning: GEMINI_API_KEY environment variable is not set.")
except Exception as e:
    print(f"Failed to initialize Gemini AI: {e}")
    chat = None

# Initialize YOLO model
try:
    model = YOLO("best.pt")
except Exception as e:
    print(f"Failed to load YOLO model: {e}")
    model = None

# Note: StaticFiles mount moved to the bottom

@app.post("/analyze")
async def analyze_image(file: UploadFile = File(...)):
    if not model:
        return JSONResponse(status_code=500, content={"error": "YOLO model not loaded"})
    
    try:
        # Read the uploaded image
        contents = await file.read()
        
        # Save temp file
        temp_img_path = f"temp_{file.filename}"
        with open(temp_img_path, "wb") as f:
            f.write(contents)
            
        # Run inference
        results = model([temp_img_path])
        
        # Extract features and aggregate
        result = results[0]  # first image
        aggregated_data = {}
        boxes = result.boxes
        if boxes:
            for box in boxes:
                cls_id = int(box.cls[0].item())
                conf = float(box.conf[0].item())
                class_name = model.names[cls_id]
                if class_name not in aggregated_data:
                    aggregated_data[class_name] = {"count": 0, "sum_conf": 0.0}
                aggregated_data[class_name]["count"] += 1
                aggregated_data[class_name]["sum_conf"] += conf
                
        extracted_results = []
        overall_max_avg_conf = 0.0
        
        for class_name, data in aggregated_data.items():
            avg_conf = data["sum_conf"] / data["count"]
            if avg_conf > overall_max_avg_conf:
                overall_max_avg_conf = avg_conf
            extracted_results.append({
                "disease": class_name,
                "count": data["count"],
                "avg_confidence_val": avg_conf,
                "confidence": f"{avg_conf:.2%}"
            })
                
        # Get image with bounding boxes drawn
        res_img = result.plot()
        
        # Encode to base64
        _, buffer = cv2.imencode('.jpg', res_img)
        img_str = base64.b64encode(buffer).decode('utf-8')
        
        # Clean up
        os.remove(temp_img_path)
        
        # Medical Risk Level + Recommendation
        if extracted_results:
            if overall_max_avg_conf > 0.75:
                risk_level = "HIGH"
                primary_rec = "Consult doctor immediately"
            elif overall_max_avg_conf >= 0.50:
                risk_level = "MODERATE"
                primary_rec = "Further tests needed"
            else:
                risk_level = "LOW"
                primary_rec = "Monitor symptoms"
        else:
            risk_level = "NONE"
            primary_rec = "Maintain regular health checkups"
            
        recommendations = [primary_rec]
        for r in extracted_results:
            d = r['disease'].lower()
            if 'nodule' in d:
                recommendations.append("Follow-up scan recommended. Consult a pulmonologist for further evaluation.")
            elif 'tuberculosis' in d:
                recommendations.append("Immediate medical attention required. Isolate and begin prescribed antibiotic therapy.")
            elif 'tumor' in d:
                recommendations.append("Urgent biopsy and oncology referral is recommended.")
                
        return JSONResponse(content={
            "success": True,
            "detected": extracted_results,
            "risk_level": risk_level,
            "risk_recommendation": primary_rec,
            "recommendations": list(set(recommendations)),
            "result_image_base64": img_str
        })
        
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

class ChatMessage(BaseModel):
    message: str

def detect_language(text):
    for char in text:
        if '\u0c00' <= char <= '\u0c7f':
            return 'Telugu'
        elif '\u0900' <= char <= '\u097f':
            return 'Hindi'
    return 'English'

def get_fallback_ai_response(query: str, lang: str):
    # Try free AI generation endpoint first
    try:
        sys_prompt = f"You are a helpful and intelligent AI assistant. Respond in the language '{lang}'. Be extremely concise. "
        full_query = sys_prompt + query
        url = f"https://text.pollinations.ai/{urllib.parse.quote(full_query)}"
        headers = {'User-Agent': 'LungVisionAI/1.0 (contact@lungvision.ai)'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=8) as response:
            answer = response.read().decode('utf-8').strip()
            if answer:
                return answer
    except Exception as e:
        print("Pollinations AI Fallback Error:", e)

    # Secondary fallback to Wikipedia
    try:
        headers = {'User-Agent': 'LungVisionAI/1.0 (contact@lungvision.ai)'}
        search_url = f"https://en.wikipedia.org/w/api.php?action=query&list=search&srsearch={urllib.parse.quote(query)}&utf8=&format=json"
        req = urllib.request.Request(search_url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            search_results = data.get('query', {}).get('search', [])
            if not search_results:
                return "I couldn't find specific information on that topic currently."
            title = search_results[0]['title']
            
        summary_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{urllib.parse.quote(title)}"
        req2 = urllib.request.Request(summary_url, headers=headers)
        with urllib.request.urlopen(req2, timeout=5) as response:
            data = json.loads(response.read().decode())
            return data.get('extract', f"Found an article about {title}, but couldn't load the text.")
    except Exception as e:
        return f"I experienced a slight issue fetching the information offline: {str(e)}"

@app.post("/chat")
async def chat_with_ai(chat_message: ChatMessage):
    user_msg = chat_message.message
    lang = detect_language(user_msg)
    
    prompt = (f"You are a helpful and intelligent General Purpose AI assistant. "
              f"You answer ANY type of questions, including health, agriculture, education, technology, and general topics. "
              f"Instruction: Answer in the same language as the user's question ({lang}) exclusively. "
              f"User input: '{user_msg}'")
              
    if chat:
        try:
            response = chat.send_message(prompt)
            if response.text:
                return JSONResponse(content={"response": response.text})
        except Exception as e:
            print("Gemini API Error:", e)
            pass # fallback triggered below
            
    # Fallback System (NO FAILURE): Free Pollinations AI / Wikipedia
    try:
        fallback_resp = "(Free Search Mode) " + get_fallback_ai_response(user_msg, lang)
        return JSONResponse(content={"response": fallback_resp})
    except Exception as e:
        return JSONResponse(content={"response": f"(Free Search Mode) I am an AI assistant here to help. Note: main API is currently offline."})

class ReportData(BaseModel):
    name: str
    age: str
    sex: str
    email: str
    mobile: str
    detected: List[dict]
    recommendations: List[str]
    risk_level: str
    risk_recommendation: str
    image_base64: str
    original_image_base64: str = ""

@app.post("/download-report")
async def download_report(data: ReportData):
    try:
        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        
        c.setFont("Helvetica-Bold", 22)
        c.drawString(50, 750, "LungVision AI - Medical Report")
        
        c.setFont("Helvetica", 10)
        c.drawString(50, 730, f"Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        c.line(50, 720, 550, 720)
        
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, 700, "Patient Information")
        
        c.setFont("Helvetica", 12)
        c.drawString(50, 680, f"Name: {data.name}")
        c.drawString(300, 680, f"Age: {data.age} | Sex: {data.sex}")
        c.drawString(50, 660, f"Email: {data.email}")
        c.drawString(300, 660, f"Mobile: {data.mobile}")
        
        c.line(50, 650, 550, 650)
        
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, 620, "AI Analysis Findings")
        
        y = 600
        c.setFont("Helvetica", 12)
        if data.detected:
            for d in data.detected:
                c.drawString(50, y, f"- Detected: {str(d.get('disease', '')).upper()} (Confidence: {d.get('confidence', '')})")
                y -= 20
        else:
            c.drawString(50, y, "- No specific diseases detected with high confidence.")
            y -= 20
            
        y -= 10
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, "Risk Assessment")
        y -= 20
        c.setFont("Helvetica-Bold", 12)
        if data.risk_level == 'HIGH':
            c.setFillColorRGB(0.8, 0, 0) # Red
        elif data.risk_level == 'MODERATE':
            c.setFillColorRGB(0.8, 0.4, 0) # Orange
        elif data.risk_level == 'LOW':
            c.setFillColorRGB(0, 0.5, 0) # Green
        else:
            c.setFillColorRGB(0, 0, 0) # Black
            
        c.drawString(50, y, f"Risk Level: {data.risk_level}")
        c.setFillColorRGB(0, 0, 0) # Reset to Black
        c.setFont("Helvetica", 12)
        c.drawString(200, y, f"Recommendation: {data.risk_recommendation}")
        y -= 30
            
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y, "Recommendations")
        y -= 20
        
        c.setFont("Helvetica", 12)
        if data.recommendations:
            for r in data.recommendations:
                if y < 100:
                    c.showPage()
                    y = 750
                c.drawString(50, y, f"* {r}") # Wrap simple
                y -= 20
        
        if y < 300:
            c.showPage()
            y = 750
            
        c.setFont("Helvetica-Bold", 14)
        c.drawString(50, y - 20, "Scan Details")
        y -= 50
        
        # Add original and analyzed images horizontally
        try:
            if data.original_image_base64:
                img_data_orig = base64.b64decode(data.original_image_base64)
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_img_orig:
                    temp_img_orig.write(img_data_orig)
                    temp_img_orig_path = temp_img_orig.name
                    
                c.setFont("Helvetica", 12)
                c.drawString(50, y + 10, "Original Uploaded Scan")
                c.drawImage(temp_img_orig_path, 50, y - 180, width=220, height=180)
                os.remove(temp_img_orig_path)
            
            if data.image_base64:
                img_data_analyzed = base64.b64decode(data.image_base64)
                with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as temp_img_analyzed:
                    temp_img_analyzed.write(img_data_analyzed)
                    temp_img_analyzed_path = temp_img_analyzed.name
                    
                c.setFont("Helvetica", 12)
                c.drawString(300, y + 10, "Analyzed Scan")
                c.drawImage(temp_img_analyzed_path, 300, y - 180, width=220, height=180)
                os.remove(temp_img_analyzed_path)
        except Exception as e:
            print(f"Error adding images to PDF: {e}")
                
        c.save()
        buffer.seek(0)
        
        return StreamingResponse(
            buffer, 
            media_type="application/pdf", 
            headers={"Content-Disposition": f'attachment; filename="{data.name.replace(" ", "_")}_Lung_Report.pdf"'}
        )
    except Exception as e:
        traceback.print_exc()
        return JSONResponse(status_code=500, content={"error": str(e)})

# Mount frontend directory for static files (must be at the bottom to prevent shadowing api routes)
app.mount("/", StaticFiles(directory="frontend", html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
