import os
from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from flask_bcrypt import Bcrypt
from dotenv import load_dotenv
import fitz
import google.generativeai as genai

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

# --- DATABASE MODEL ---
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(60), nullable=False)

# --- ROADMAP DATA ---
ROADMAP_DATA = {
    "web-dev": {
        "title": "Full Stack Web Development",
        "description": "This path provides a comprehensive journey from frontend aesthetics to backend logic, preparing you to build and deploy complete web applications.",
        "steps": [
            {"title": "Module 1: Foundations - HTML, CSS, & Git", "description": "Learn the core structure of web pages with HTML, style them with CSS, and manage your code with Git version control."},
            {"title": "Module 2: JavaScript Fundamentals", "description": "Master the programming language of the web for interactive and dynamic content."},
            {"title": "Module 3: Frontend Frameworks (React)", "description": "Build modern, fast, and scalable user interfaces by learning the component-based architecture of React."},
            {"title": "Module 4: Backend Development (Python & Flask)", "description": "Create powerful servers, RESTful APIs, and handle server-side logic using the Flask framework."},
            {"title": "Module 5: Databases & SQL", "description": "Learn to design, manage, and query relational databases to store and retrieve application data effectively."},
            {"title": "Module 6: Deployment & Cloud Basics", "description": "Understand how to take your application live using cloud services and basic DevOps principles."}
        ],
        "jobs": ["Frontend Developer", "Backend Developer", "Full Stack Developer", "Web Application Engineer"]
    },
    "ml-eng": { "title": "Machine Learning Engineer", "description": "This path covers the essential skills for a career in Artificial Intelligence.", "steps": [], "jobs": ["Machine Learning Engineer", "Data Scientist", "AI Developer"] },
    "devops": { "title": "Cloud & DevOps Engineer", "description": "Learn to automate, deploy, and scale modern software applications in the cloud.", "steps": [], "jobs": ["DevOps Engineer", "Cloud Engineer", "Site Reliability Engineer (SRE)"] }
}

@app.cli.command("init-db")
def init_db():
    with app.app_context():
        db.create_all()
    print("Initialized the database.")

# --- PAGE ROUTES ---
@app.route("/")
def index(): return render_template("login.html")

@app.route("/courses")
def courses():
    if 'user_id' not in session: return redirect(url_for('index'))
    return render_template("courses.html")

@app.route("/course/<course_id>")
def course_roadmap(course_id):
    if 'user_id' not in session: return redirect(url_for('index'))
    roadmap = ROADMAP_DATA.get(course_id)
    if not roadmap: return "Course not found!", 404
    return render_template("roadmap.html", roadmap=roadmap)

@app.route("/chat")
def chat():
    if 'user_id' not in session: return redirect(url_for('index'))
    return render_template("chat.html")

# --- AUTHENTICATION ROUTES ---
@app.route("/signup", methods=["POST"])
def signup():
    name, email, password = request.form.get('name'), request.form.get('email'), request.form.get('password')
    if User.query.filter_by(email=email).first():
        return render_template("login.html", error="Email already registered.", form='signup')
    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')
    new_user = User(name=name, email=email, password=hashed_password)
    db.session.add(new_user)
    db.session.commit()
    session['user_id'] = new_user.id
    return redirect(url_for('courses'))

@app.route("/login", methods=["POST"])
def login():
    email, password = request.form.get('email'), request.form.get('password')
    user = User.query.filter_by(email=email).first()
    if user and bcrypt.check_password_hash(user.password, password):
        session['user_id'] = user.id
        return redirect(url_for('courses'))
    else:
        return render_template("login.html", error="Invalid email or password.", form='login')

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('index'))

# --- AI API ENDPOINTS ---

@app.route("/mentor-chat", methods=["POST"])
def mentor_chat():
    if 'user_id' not in session: return jsonify({"error": "Not logged in"}), 401
    data = request.get_json()
    question, course_title = data.get("question"), data.get("course_title")
    if not question or not course_title: return jsonify({"error": "Missing data"}), 400
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    prompt = (f"You are an expert AI mentor for a course titled '{course_title}'. "
              f"A student asked: '{question}'. Provide a helpful, clear, and encouraging explanation. "
              f"If asked for more courses, suggest 1-2 specific online courses related to '{course_title}'.")
    response = model.generate_content(prompt)
    return jsonify({"answer": response.text})

@app.route("/summarize-pdf", methods=["POST"])
def summarize_pdf():
    if 'user_id' not in session: return jsonify({"error": "Not logged in"}), 401
    if 'pdf_file' not in request.files: return jsonify({"error": "No file part"}), 400
    file = request.files['pdf_file']
    if file.filename == '' or not file.filename.endswith('.pdf'): return jsonify({"error": "Invalid file"}), 400
    try:
        pdf_document = fitz.open(stream=file.read(), filetype="pdf")
        full_text = "".join(page.get_text() for page in pdf_document)
        pdf_document.close()
        if not full_text.strip(): return jsonify({"summary": "This PDF contains no text to summarize."})
        
        model = genai.GenerativeModel('gemini-1.5-flash-latest')
        prompt = f"Summarize the following document into key bullet points:\n\n{full_text}"
        response = model.generate_content(prompt)
        return jsonify({"summary": response.text})
    except Exception as e:
        return jsonify({"error": f"Error processing PDF: {str(e)}"}), 500

@app.route("/summarize", methods=["POST"])
def summarize():
    if 'user_id' not in session: return jsonify({"error": "Not logged in"}), 401
    data = request.get_json()
    text = data.get("text")
    if not text: return jsonify({"error": "No text provided"}), 400
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    prompt = f"Summarize the following text into a few key bullet points:\n\n{text}"
    response = model.generate_content(prompt)
    return jsonify({"summary": response.text})

@app.route("/recommend-courses", methods=["POST"])
def recommend_courses():
    if 'user_id' not in session: return jsonify({"error": "Not logged in"}), 401
    data = request.get_json()
    subject = data.get("subject")
    if not subject: return jsonify({"error": "Subject is required"}), 400
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    prompt = (f"Act as an expert student counselor. A user is interested in '{subject}'. "
              f"Suggest 3 relevant online courses from popular platforms. For each course, provide: "
              f"1. Title. 2. Platform. 3. A short description. 4. A Google search link. "
              f"Format the entire output in Markdown, with the title as a heading and the link as a clickable URL.")
    response = model.generate_content(prompt)
    return jsonify({"recommendation": response.text})

@app.route("/brainstorm-career", methods=["POST"])
def brainstorm_career():
    if 'user_id' not in session: return jsonify({"error": "Not logged in"}), 401
    data = request.get_json()
    skills = data.get("skills")
    if not skills: return jsonify({"error": "Skills are required"}), 400
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    prompt = (f"Act as a creative career coach. A user has skills/interests in '{skills}'. "
              f"Brainstorm 3-5 interesting career paths. For each one, provide a brief description of why it's a good match.")
    response = model.generate_content(prompt)
    return jsonify({"career_ideas": response.text})

if __name__ == "__main__":
    app.run(debug=True)