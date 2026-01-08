# matutor/views.py
import os
import json
import traceback
import logging
import shutil
import time
import re
from django.conf import settings
from django.http import (
    JsonResponse,
    HttpResponseBadRequest,
    HttpResponseNotFound,
    FileResponse,
)
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

# from .tts_service import TTSService

logger = logging.getLogger(__name__)
# Define temp directory for Wolfram scripts
WOLFRAM_TEMP_DIR = os.path.join(os.path.dirname(__file__), "temp")
os.makedirs(WOLFRAM_TEMP_DIR, exist_ok=True)

MEDIA_DIR = os.path.join(os.path.dirname(__file__), "media")
os.makedirs(MEDIA_DIR, exist_ok=True)
# Single shared TTS service instance (lazy-loads the TTS model on first use)
# tts_service = TTSService()

# Maximum allowed characters in the text payload (protects from very long requests)
MAX_TEXT_LENGTH = 5000


def index(request):
    """Simple index/help endpoint."""
    return JsonResponse(
        {
            "message": "matutor TTS API — POST /api/tts/ with JSON {'text':'...'}",
            "notes": "Generated audio is served from MEDIA_URL (development only).",
        }
    )


# @csrf_exempt  # remove or secure in production
# @require_POST
# def synthesize(request):
#     """
#     POST /api/tts/
#     Body (JSON): {"text": "some text to synthesize"}
#     Response: {"success": True, "filename": "tts_xxx.wav", "url": "http://.../media/tts_xxx.wav"}
#     """
#     # parse JSON body
#     try:
#         payload = json.loads(request.body.decode("utf-8"))
#     except Exception:
#         return HttpResponseBadRequest("Invalid JSON body")

#     text = payload.get("text", "")
#     if not isinstance(text, str) or not text.strip():
#         return HttpResponseBadRequest("Field 'text' is required and must be non-empty")

#     if len(text) > MAX_TEXT_LENGTH:
#         return HttpResponseBadRequest(f"Text too long (max {MAX_TEXT_LENGTH} characters)")

#     try:
#         # Generate WAV file (returns absolute filesystem path)
#         out_path = tts_service.generate(text)
#         filename = os.path.basename(out_path)

#         # Build absolute URL so clients (Postman/browser) can open it
#         media_url = settings.MEDIA_URL if hasattr(settings, "MEDIA_URL") else "/media/"
#         # request.build_absolute_uri handles host/port
#         file_url = request.build_absolute_uri(os.path.join(media_url, filename))

#         return JsonResponse({"success": True, "filename": filename, "url": file_url})
#     except Exception as exc:
#         logger.exception("TTS generation failed")
#         return JsonResponse({"success": False, "error": str(exc)}, status=500)


# def get_audio(request, filename):
#     """
#     Optional direct file endpoint: /media/<filename> (or configured via urls)
#     Returns the generated WAV file, or 404 if missing.
#     """
#     media_root = getattr(settings, "MEDIA_ROOT", os.path.join(os.path.dirname(os.path.dirname(_file_)), "media"))
#     path = os.path.join(media_root, filename)

#     if not os.path.exists(path):
#         return HttpResponseNotFound("File not found")

#     return FileResponse(open(path, "rb"), content_type="audio/wav")


# matutor/views.py
import os
import google.generativeai as genai

from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from django.conf import settings


# Configure Gemini with API key from settings
genai.configure(api_key=settings.GEMINI_API_KEY)


@csrf_exempt
@require_POST
def image_to_text(request):
    """
    Endpoint: POST /api/image-to-text/
    Accepts: multipart/form-data with 'image' field
    Returns: JSON { "text": "..." }
    """
    if "image" not in request.FILES:
        return HttpResponseBadRequest("No image uploaded")

    image_file = request.FILES["image"]

    try:
        # Convert uploaded file into bytes
        image_bytes = image_file.read()

        # Load model (Gemini Pro Vision)
        model = genai.GenerativeModel("gemini-2.0-flash-exp")

        # Call Gemini with image
        response = model.generate_content([
        {"mime_type": image_file.content_type, "data": image_bytes},
        "Extract ONLY the exact text from this image. Do not add descriptions, interpretations, or summaries. If no text is found, return an empty string."])


        # Extract text response
        text_output = response.text if response and hasattr(response, "text") else ""

        return JsonResponse({"text": text_output})

    except Exception as e:
        return JsonResponse({"error": str(e)}, status=500)


import os
import json
import subprocess
import tempfile
import logging
import traceback
import time
from groq import Groq
import google.generativeai as genai

from django.conf import settings
from django.http import JsonResponse, HttpResponseBadRequest
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST


def build_groq_system_prompt() -> str:
    return """
You are an advanced mathematical problem solver. Your goal is to solve the user's problem step-by-step and return the final answer.

CRITICAL OUTPUT FORMAT:
You must return a valid JSON object with the following structure:
{
    "result": <numerical_or_symbolic_result>,
    "steps": [
        "step 1 description",
        "step 2 description"
    ]
}

Do not include any markdown formatting (like ```json) or chatty introductory text. Just the raw JSON string.
If the result is a number, return it as a number. If it's an equation or symbolic, return as a string.
"""
import sys

@csrf_exempt
@require_POST
def solve_problem(request):
    problem_text = request.POST.get("problem")
    if not problem_text:
        return HttpResponseBadRequest("Missing 'problem' field")

    success, results_json, error_info = run_groq_solver(problem_text)
    
    if not success:
        return JsonResponse(error_info, status=500)
    
    return JsonResponse({"results": results_json})
    
import os
import sys
import json
import tempfile
import subprocess
from django.http import JsonResponse, HttpResponseBadRequest, FileResponse
from django.conf import settings
import google.generativeai as genai

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MEDIA_DIR = os.path.join(settings.BASE_DIR, "media")
os.makedirs(MEDIA_DIR, exist_ok=True)

def build_manim_prompt(problem_text: str, results_json: dict) -> str:
    results_str = json.dumps(results_json, indent=2)
    return f"""
You are a Manim animation expert and high school astronomy/mathematics educator. Your task is to take any input problem (a high school level astronomy or math calculation question) and directly generate a fully working Manim Community Edition v0.18+ Python script that can be copy-pasted and rendered to produce an educational video.

⚡ Key Instructions:

1. Output Format: Always reply ONLY with the Manim Python script in plain text (no explanations, no markdown fences, no extra commentary).
2. The user will provide the problem statement, and you must convert it directly into a complete Manim script.

## VIDEO CONFIGURATION

Always use these settings:

```python
from manim import *
import numpy as np

# Video quality settings - 480p at 15fps
config.tex_compiler = "pdflatex"
config.pixel_width = 854
config.pixel_height = 480
config.frame_rate = 15
```

## VALID MANIM COLORS

ONLY use these predefined Manim color constants. NEVER invent color names:
- Basic: WHITE, BLACK, GRAY, GREY, RED, GREEN, BLUE, YELLOW, ORANGE, PURPLE, PINK
- Gray shades: LIGHT_GRAY, DARK_GRAY, DARKER_GRAY, LIGHT_GREY, DARK_GREY, DARKER_GREY
- Blue variants: BLUE_A, BLUE_B, BLUE_C, BLUE_D, BLUE_E
- Teal variants: TEAL, TEAL_A, TEAL_B, TEAL_C, TEAL_D, TEAL_E
- Green variants: GREEN_A, GREEN_B, GREEN_C, GREEN_D, GREEN_E
- Yellow variants: YELLOW_A, YELLOW_B, YELLOW_C, YELLOW_D, YELLOW_E
- Gold variants: GOLD, GOLD_A, GOLD_B, GOLD_C, GOLD_D, GOLD_E
- Red variants: RED_A, RED_B, RED_C, RED_D, RED_E
- Maroon variants: MAROON, MAROON_A, MAROON_B, MAROON_C, MAROON_D, MAROON_E
- Purple variants: PURPLE_A, PURPLE_B, PURPLE_C, PURPLE_D, PURPLE_E
- Pink variants: PINK, LIGHT_PINK

⚠️ CRITICAL: Colors like GREEN_SCREEN, NEON_GREEN, BRIGHT_BLUE, etc. DO NOT EXIST. Use only the colors listed above.

## SCREEN LAYOUT REQUIREMENTS

Divide screen into 3 distinct sections:

- TOP SECTION (0.8 to 1.0 of screen height): Main titles and headers only
- MIDDLE SECTION (0.2 to 0.8 of screen height): Main content, calculations, diagrams, processes
- BOTTOM SECTION (0.0 to 0.2 of screen height): Subtitles and explanatory text only

Proper positioning:

```python
# Top section positioning
title.to_edge(UP, buff=0.1)

# Middle section positioning
content.move_to(ORIGIN).shift(UP * 0.1)

# Bottom section positioning
subtitle.to_edge(DOWN, buff=0.1)
```

## ANIMATION CLEANUP RULES

CRITICAL: Always clean up before new content:

```python
# Before showing new content, ALWAYS remove old elements:
Each frame should only show relevant content
Remove ALL non relevant previous elements before introducing new ones
Fade previous content before adding new content to avoid overlapping and messy visuals
Never let elements accumulate

self.play(FadeOut(old_title, old_content, old_subtitle))
self.remove(old_title, old_content, old_subtitle)  # Ensure complete removal

# Then add new content
self.play(FadeIn(new_title, new_content, new_subtitle))
```

Sequential content management:
- Each frame should only show relevant content
- Remove ALL previous elements before introducing new ones
- Use FadeOut() followed by self.remove() for complete cleanup
- Never let elements overlap or accumulate

## API COMPATIBILITY RULES

Use current Manim Community syntax:
- Use self.add() instead of self.add_fixed_in_frame_mobjects()
- Use self.remove() instead of self.remove_fixed_in_frame_mobjects()
- Import from manim import * (not from manimlib import *)
- Use Scene class (not ThreeDScene unless specifically needed for 3D)

## SCENE STRUCTURE TEMPLATE

Follow this structure:

```python
class PhysicsProblem(Scene):
    def construct(self):
        # Set background
        self.camera.background_color = BLACK
        
        # Section 1: Title
        title = Text("Title", font_size=36, color=YELLOW).to_edge(UP, buff=0.1)
        self.play(Write(title))
        
        # Section 2: Main content
        content = MathTex("formula", color=TEAL).move_to(ORIGIN)
        self.play(Write(content))
        
        # Section 3: Subtitle
        subtitle = Text("explanation", font_size=24, color=WHITE).to_edge(DOWN, buff=0.1)
        self.add(subtitle)
        self.play(FadeIn(subtitle))
        
        # Cleanup before next section
        self.play(FadeOut(title, content, subtitle))
        self.remove(title, content, subtitle)
        
        # Next section...
```

## TEXT AND LAYOUT BEST PRACTICES

Proper text sizing for 480p:

```python
# Titles (top section)
title = Text("Main Title", font_size=36, color=YELLOW).to_edge(UP, buff=0.1)

# Main content (middle section)
content = MathTex(r"\\theta = 2 \\arctan\\left(\\frac{{D}}{{2d}}\\right)", font_size=32, color=TEAL).move_to(ORIGIN)

# Subtitles (bottom section)
subtitle = Text("Explanation text", font_size=24, color=WHITE).to_edge(DOWN, buff=0.1)
```

Avoid overlapping:
- Use .next_to() with proper buff values
- Use .align_to() for consistent alignment
- Use VGroup() to group related elements
- For bigger texts, split into multiple lines instead of exceeding screen width

## ANIMATION BUILDING BLOCKS

Math Expressions:

```python
equation = MathTex(r"E = mc^2", font_size=32, color=BLUE).move_to(ORIGIN)
self.play(Write(equation))

# To highlight results:
box = SurroundingRectangle(equation, buff=0.15, color=YELLOW, stroke_width=3)
self.play(Create(box))
```

Showing Steps with Transform:

```python
eq1 = MathTex(r"E = mc^2", color=WHITE)
eq2 = MathTex(r"E = (2)(3)^2", color=WHITE)
self.play(Write(eq1))
self.wait(1)
self.play(Transform(eq1, eq2))
```

Shapes & Geometry:

```python
circle = Circle(radius=2, color=TEAL)
line = Line(LEFT, RIGHT, color=YELLOW)
arc = Arc(radius=1, start_angle=0, angle=PI/3, color=ORANGE)
dot = Dot(color=RED)
```

## SCENE FLOW / BEST PRACTICES

The script should follow this sequence:

1. Intro Title & Subtitle (problem statement)
2. Display Givens (list of knowns)
3. Show Formula (highlighted, maybe boxed)
4. Step-by-Step Substitution (use Transform to morph equations)
5. Final Result (boxed, large font, color highlight)
6. Optional Visualization (diagrams, circuits, etc.)
7. Summary Slide (results recap)

## VALID ANIMATIONS TO USE

- Write()
- FadeIn()
- FadeOut()
- Transform()
- ReplacementTransform()
- Create() (for lines/shapes)
- GrowFromCenter()
- self.wait(time) for pacing
- SurroundingRectangle() for highlights

## TEXT AND MATHTEX FORMATTING

- Use raw strings for LaTeX: r"\\\\theta = 2 \\\\arctan\\\\left(\\\\frac{{D}}{{2d}}\\\\right)"
- Escape backslashes properly in f-strings: f"{{value:.3f}}^\\\\\\\\circ"
- Use MathTex for mathematical expressions
- Use Text for regular text

## TIMING/PACING

- Animations 0.5–2s each
- Use self.wait(0.5–1) sparingly
- Total runtime optimized for 5–8 minutes at 1x

## CRITICAL: MATH TEX STRING FORMATTING RULES

NEVER use .format() with MathTex when mixing LaTeX and variables:

❌ WRONG - This causes KeyError:
```python
step3 = MathTex(r"\\theta = 2 \\arctan\\left({{:f}}\\right)".format(val))
```

✅ CORRECT - Use string concatenation:
```python
step3 = MathTex(r"\\theta = 2 \\arctan\\left(" + f"{{val:.6f}}" + r"\\right)")
```

### PROPER MATH TEX FORMATTING PATTERNS

For single variables:
```python
# Correct
result = MathTex(r"\\theta \\approx " + f"{{theta_deg:.2f}}" + r"^\\circ", color=GREEN)

# Wrong
result = MathTex(r"\\theta \\approx {{:.2f}}^\\circ".format(theta_deg))
```

For multiple variables:
```python
# Correct
equation = MathTex(r"E = " + f"{{mass:.1f}}" + r" \\times " + f"{{speed:.0f}}" + r"^2", color=BLUE)
```

### WHY THIS MATTERS

- LaTeX uses {{}} for grouping, which conflicts with Python's .format() syntax
- String concatenation with f-strings is the safest approach
- This prevents KeyError exceptions during rendering

## ERROR PREVENTION CHECKLIST

Before using MathTex with variables:
1. ✅ Use string concatenation instead of .format()
2. ✅ Use f-strings for number formatting
3. ✅ Keep LaTeX and Python formatting separate
4. ✅ Always specify a valid color from the approved list

Common issues to avoid:
- ❌ Undefined colors (GREEN_SCREEN, NEON_GREEN, etc.)
- ❌ stroke_dash_offset parameter (doesn't exist)
- ❌ align_to=LEFT in next_to() (use aligned_edge=LEFT)

## CRITICAL MISTAKES TO AVOID

NEVER:
- Use undefined color constants
- Let text overlap between sections
- Skip cleanup between scenes
- Use deprecated API methods
- Mix old and new content without proper removal
- Use incorrect video dimensions (always 480p, 15fps)
- Use deprecated syntax like TexText, ShowCreation
- Leave undefined variables
- Use .format() with MathTex containing LaTeX

Rules for generating Manim scripts:

Do not directly index into MathTex or Tex submobjects using numeric indices (like [0][4], [2][3]).

If you want to highlight or surround a part of an equation, use:

get_part_by_tex("symbol") for targeting a specific symbol, e.g. eq.get_part_by_tex("R").

Or surround the whole object with SurroundingRectangle(eq).

If you must use indexing, always check len(eq) first before accessing submobjects.

When animating highlights across multiple equations, prefer VGroup(eq1, eq2, eq3) instead of indexing into sub-elements.

Always prioritize readability and stability of the script over fancy indexing.

🔧 Example (before vs after)
❌ Bad (indexing, can crash):
SurroundingRectangle(currents_calc[0][4])

✅ Good (robust):
SurroundingRectangle(currents_calc[0])  
# or
currents_calc[0].get_part_by_tex("I")

ALWAYS:
- Use only valid Manim color constants
- Clean up completely before new content
- Use proper section positioning
- Use appropriate font sizes for 480p
- Remove elements with both FadeOut() and self.remove()
- Use current Manim Community API
- Use string concatenation with f-strings for MathTex

## OUTPUT REQUIREMENTS

Always provide:
1. Complete, runnable code with 480p/15fps settings
2. Proper 3-section layout implementation
3. Complete cleanup between scenes
4. Current API methods only
5. No overlapping text elements
6. Clear comments for each section
7. Equations that compile with LaTeX
8. No undefined variables or syntax errors
9. Only valid Manim color constants
10. Final script must run standalone with Manim CE

---
⚠️ Do not use any undefined variables. Always reference actual objects created in the scene.
Remember: Use ONLY valid Manim colors, clean up completely before each new scene, maintain 3-section layout, always use 480p/15fps configuration, and use string concatenation for MathTex with variables.

Problem Text:
{problem_text}

Results JSON:
{results_str}
"""


def build_transcript_prompt(manim_script: str, problem_text: str, results_json: dict) -> str:
    results_str = json.dumps(results_json, indent=2)
    return f"""
You are an expert educational narrator. Analyze the provided Manim animation script and create a natural, engaging voiceover transcript that explains the problem and solution step-by-step.

INSTRUCTIONS:
1. Analyze the Manim script to understand the visual flow and timing
2. Create a clear, conversational narration that follows the animation
3. Keep it concise but educational - aim for 2-4 minutes of speech
4. Use simple language suitable for high school students
5. Explain each step as it appears in the animation
6. Mention key values and results from the calculations
7. Make it engaging and easy to follow
8. Do NOT include any markdown, labels, or formatting - just plain speech text

MANIM SCRIPT:
{manim_script}

ORIGINAL PROBLEM:
{problem_text}

CALCULATED RESULTS:
{results_str}

Generate a natural voiceover script that a teacher would use to narrate this animation. Output ONLY the transcript text, no markdown, no labels, just the speech text that should be spoken.
"""



# @csrf_exempt
# @require_POST
# def generate_video(request):
#     if request.method != "POST":
#         return HttpResponseBadRequest("Only POST allowed")

#     # Try to parse JSON body first, then fall back to form data
#     problem_text = None
    
#     try:
#         if request.content_type == 'application/json':
#             data = json.loads(request.body.decode('utf-8'))
#             problem_text = data.get("problem")
#         else:
#             problem_text = request.POST.get("problem")
#     except (json.JSONDecodeError, UnicodeDecodeError) as e:
#         return HttpResponseBadRequest(f"Invalid request format: {str(e)}")

#     if not problem_text:
#         return HttpResponseBadRequest("Missing 'problem' field")

#     # Generate unique filenames
#     timestamp = int(time.time() * 1000)
#     solver_filename = f"wolfram_solver_{timestamp}.py"
#     manim_filename = f"manim_script_{timestamp}.py"
#     solver_path = os.path.join(WOLFRAM_TEMP_DIR, solver_filename)
#     manim_path = os.path.join(WOLFRAM_TEMP_DIR, manim_filename)
    
#     try:
#         # ===== STEP 1: SOLVE THE PROBLEM WITH WOLFRAM =====
#         model = genai.GenerativeModel("gemini-2.5-flash")
#         response = model.generate_content(build_gemini_prompt(problem_text))

#         # Extract Python code (strip markdown if present)
#         code_text = response.text.strip()
#         if code_text.startswith("python"):
#             code_text = code_text[len("python"):].strip()
#         if code_text.endswith(""):
#             code_text = code_text[:-3].strip()

#         # Write solver code to temp folder
#         with open(solver_path, "w", encoding="utf-8") as f:
#             f.write(code_text)

#         # Run the Wolfram solver script
#         proc = subprocess.run(
#             [sys.executable, solver_path],
#             capture_output=True,
#             text=True,
#             timeout=60,  # Increased timeout for Wolfram
#             encoding="utf-8",
#             errors="replace"
#         )

#         # Handle solver errors
#         if proc.returncode != 0:
#             return JsonResponse({
#                 "error": "Wolfram solver failed",
#                 "details": proc.stderr.strip(),
#                 "solver_file": solver_filename
#             }, status=500)

#         # Extract JSON from solver output
#         stdout_clean = proc.stdout.strip()
#         json_start = stdout_clean.find("{")
#         json_end = stdout_clean.rfind("}") + 1
#         if json_start == -1 or json_end == -1:
#             return JsonResponse({
#                 "error": "No JSON output found",
#                 "raw": stdout_clean,
#                 "solver_file": solver_filename
#             }, status=500)

#         try:
#             results_json = json.loads(stdout_clean[json_start:json_end])
#         except json.JSONDecodeError as e:
#             return JsonResponse({
#                 "error": f"Invalid JSON: {str(e)}",
#                 "raw": stdout_clean,
#                 "solver_file": solver_filename
#             }, status=500)

#         # ===== STEP 2: GENERATE MANIM SCRIPT =====
#         manim_prompt = build_manim_prompt(problem_text, results_json)
#         manim_response = model.generate_content(manim_prompt)
#         script_text = manim_response.text.strip()

#         # Remove markdown fences
#         if script_text.startswith("python"):
#             script_text = script_text[len("python"):].strip()
#         if script_text.endswith(""):
#             script_text = script_text[:-3].strip()

#         # ===== STEP 2.5: EXTRACT CLASS NAME FROM SCRIPT =====
#         class_match = re.search(r'class\s+(\w+)\s*\(Scene\)', script_text)
#         if not class_match:
#             return JsonResponse({
#                 "error": "Could not find Scene class in generated script",
#                 "solver_file": solver_filename
#             }, status=500)
        
#         class_name = class_match.group(1)

#         # Write Manim script to temp folder
#         with open(manim_path, "w", encoding="utf-8") as f:
#             f.write(script_text)

#         # ===== STEP 3: RENDER VIDEO WITH MANIM =====
#         video_filename = f"manim_video_{timestamp}.mp4"
        
#         # Manim outputs to media/videos/<script_name>/<quality>/
#         script_basename = os.path.splitext(os.path.basename(manim_path))[0]
#         manim_output_dir = os.path.join("media", "videos", script_basename, "480p15")
        
#         # Run manim CLI with extracted class name
#         manim_proc = subprocess.run(
#             [sys.executable, "-m", "manim",
#              manim_path,
#              class_name,
#              "-ql",
#              "--format", "mp4",
#              "--media_dir", "media"],
#             capture_output=True,
#             text=True,
#             timeout=300,
#             encoding="utf-8",
#             errors="replace"
#         )

#         # Handle render errors
#         if manim_proc.returncode != 0:
#             return JsonResponse({
#                 "error": "Manim render failed",
#                 "details": manim_proc.stderr.strip(),
#                 "solver_file": solver_filename,
#                 "manim_file": manim_filename
#             }, status=500)

#         # Find the generated video (using dynamic class name)
#         expected_video = os.path.join(manim_output_dir, f"{class_name}.mp4")
        
#         if not os.path.exists(expected_video):
#             return JsonResponse({
#                 "error": "Video file not found after rendering",
#                 "expected_path": expected_video,
#                 "class_name": class_name,
#                 "solver_file": solver_filename,
#                 "manim_file": manim_filename
#             }, status=500)

#         # Move video to final location
#         final_video_path = os.path.join(MEDIA_DIR, video_filename)
#         os.makedirs(MEDIA_DIR, exist_ok=True)
#         shutil.move(expected_video, final_video_path)

#         # ===== STEP 4: GENERATE TRANSCRIPT FROM MANIM SCRIPT =====
#         transcript_prompt = build_transcript_prompt(script_text, problem_text, results_json)
#         transcript_response = model.generate_content(transcript_prompt)
#         transcript_text = transcript_response.text.strip()

#         return JsonResponse({
#             "results": results_json,
#             "video_file": video_filename,
#             "video_url": f"/media/{video_filename}",
#             "class_name": class_name,
#             "transcript": transcript_text,
#             "computation_engine": "Wolfram Engine",
#             "solver_file": solver_filename,
#             "manim_file": manim_filename
#         })

#     except subprocess.TimeoutExpired:
#         return JsonResponse({
#             "error": "Process timed out",
#             "solver_file": solver_filename if 'solver_filename' in locals() else None,
#             "manim_file": manim_filename if 'manim_filename' in locals() else None
#         }, status=500)
#     except Exception as e:
#         return JsonResponse({
#             "error": str(e),
#             "solver_file": solver_filename if 'solver_filename' in locals() else None,
#             "manim_file": manim_filename if 'manim_filename' in locals() else None
#         }, status=500)
#     # Note: Files are kept in temp folder for debugging


def get_video(request, filename):
    """Serve video files from multiple possible locations."""
    # Try direct MEDIA_DIR first
    video_path = os.path.join(MEDIA_DIR, filename)
    
    if not os.path.exists(video_path):
        # Try searching in media/videos subdirectories
        videos_dir = os.path.join("media", "videos","videos")
        if os.path.exists(videos_dir):
            for root, dirs, files in os.walk(videos_dir):
                if filename in files:
                    video_path = os.path.join(root, filename)
                    logger.info(f"Found video at: {video_path}")
                    break
    
    if not os.path.exists(video_path):
        logger.error(f"Video not found: {filename}")
        logger.debug(f"Searched in: {MEDIA_DIR}")
        return JsonResponse({"error": "File not found", "filename": filename}, status=404)
    
    logger.info(f"Serving video: {video_path}")
    return FileResponse(open(video_path, "rb"), content_type="video/mp4")

def build_explanation_prompt(problem_text: str, results_json: dict) -> str:
    results_str = json.dumps(results_json, indent=2)
    return f"""
You are an expert teacher explaining a physics/mathematics problem to high school students. Your task is to provide a clear, step-by-step explanation of how to solve this problem.

PROBLEM:
{problem_text}

CALCULATED RESULTS:
{results_str}

INSTRUCTIONS:
1. Start with a brief introduction explaining what type of problem this is
2. List the given information clearly
3. Explain the formula or concept needed to solve the problem
4. Break down the solution into clear, numbered steps
5. Show the calculations with explanations for each step
6. Explain WHY each step is necessary (don't just show calculations)
7. State the final answer clearly
8. Add a brief conclusion or key takeaway

FORMATTING GUIDELINES:
- Use markdown formatting for better readability
- Use **bold** for important terms and values
- Use numbered lists for steps
- Use code blocks for formulas: `formula here`
- Keep language simple and conversational
- Avoid jargon; if you must use technical terms, explain them
- Use real-world analogies when helpful
- Make it educational and easy to follow

Generate a complete step-by-step explanation that a student can easily understand and learn from.
"""
# In-memory cache for storing computation results
# Key: problem_text hash, Value: {results, timestamp}
COMPUTATION_CACHE = {}
CACHE_EXPIRY = 3600  # 1 hour in seconds


def build_gemini_prompt(problem_text: str) -> str:
    return f"""
You are a Python programming expert specializing in physics and mathematics problems using Wolfram Cloud.

⚠️ CRITICAL: Keep code SHORT and COMPLETE. Use minimal variable names and comments.

Problem: {problem_text}

Output ONLY Python code (NO code fences). Must include:
1. Imports
2. Cloud session setup
3. try-except-finally with cloud.terminate()

TEMPLATE:
import json
import os
from wolframclient.evaluation import SecuredAuthenticationKey, WolframCloudSession
from wolframclient.language import wl, wlexpr

sak = SecuredAuthenticationKey(os.getenv('WOLFRAM_CONSUMER_KEY'), os.getenv('WOLFRAM_CONSUMER_SECRET'))
cloud = WolframCloudSession(credentials=sak)

try:
    r = cloud.evaluate(wl.N(wlexpr('your_math')))
    v = float(r)
    results = {{"result": v}}
    print(json.dumps(results))
except Exception as e:
    print(json.dumps({{"error": str(e)}}))
finally:
    cloud.terminate()

RULES:
- Use wl.N() for numbers
- Short names (r, v, i, p)
- Double braces in f-strings: {{{{ }}}}
- MUST end with: cloud.terminate()

Generate code:
"""


def run_groq_solver(problem_text: str):
    """
    Run Groq solver and return results.
    Returns tuple: (success: bool, results: dict, error_info: dict)
    """
    try:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
             return False, None, {"error": "GROQ_API_KEY not found in settings"}

        client = Groq(api_key=api_key)
        
        logger.debug("Calling Groq API...")
        completion = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": build_groq_system_prompt()},
                {"role": "user", "content": problem_text}
            ],
            temperature=0,
            max_tokens=1024,
            top_p=1,
            stream=False,
            stop=None,
        )

        response_content = completion.choices[0].message.content
        logger.debug(f"Groq Response: {response_content}")

        # Basic cleanup if markdown is included despite instructions
        if "```json" in response_content:
             response_content = response_content.split("```json")[1].split("```")[0]
        elif "```" in response_content:
             response_content = response_content.split("```")[1].split("```")[0]
        
        try:
            results_json = json.loads(response_content.strip())
            return True, results_json, None
        except json.JSONDecodeError as e:
            return False, None, {
                "error": f"Invalid JSON from Groq: {str(e)}",
                "raw": response_content
            }

    except Exception as e:
        logger.exception("Unexpected error in run_groq_solver")
        return False, None, {
            "error": str(e),
            "traceback": traceback.format_exc()
        }


def get_problem_cache_key(problem_text: str) -> str:
    """Generate a cache key from problem text."""
    import hashlib
    return hashlib.md5(problem_text.encode()).hexdigest()


def get_cached_results(problem_text: str):
    """Retrieve cached results if available and not expired."""
    cache_key = get_problem_cache_key(problem_text)
    if cache_key in COMPUTATION_CACHE:
        cached = COMPUTATION_CACHE[cache_key]
        age = time.time() - cached['timestamp']
        if age < CACHE_EXPIRY:
            logger.info(f"Cache hit for problem (age: {age:.1f}s)")
            return cached['results']
        else:
            logger.info(f"Cache expired for problem (age: {age:.1f}s)")
            del COMPUTATION_CACHE[cache_key]
    return None


def set_cached_results(problem_text: str, results: dict):
    """Store results in cache."""
    cache_key = get_problem_cache_key(problem_text)
    COMPUTATION_CACHE[cache_key] = {
        'results': results,
        'timestamp': time.time()
    }
    logger.info(f"Cached results for problem (cache size: {len(COMPUTATION_CACHE)})")





@csrf_exempt
@require_POST
def explain_problem(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Only POST allowed")

    # Parse JSON body
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body.decode('utf-8'))
            problem_text = data.get("problem")
        else:
            problem_text = request.POST.get("problem")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        logger.error(f"Request parsing error: {str(e)}")
        return HttpResponseBadRequest(f"Invalid request format: {str(e)}")

    if not problem_text:
        return HttpResponseBadRequest("Missing 'problem' field")

    logger.info(f"explain_problem called for: {problem_text[:50]}...")

    # Check cache first
    cached_results = get_cached_results(problem_text)
    if cached_results:
        logger.info("Using cached results")
        
        # Generate explanation for cached results
        try:
            model = genai.GenerativeModel("gemini-2.5-flash")
            explanation_prompt = build_explanation_prompt(problem_text, cached_results)
            explanation_response = model.generate_content(explanation_prompt)
            explanation_text = explanation_response.text.strip()

            return JsonResponse({
                "problem": problem_text,
                "results": cached_results,
                "explanation": explanation_text,
                "computation_engine": "Groq Llama 3",
                "cached": True
            })
        except Exception as e:
            logger.error(f"Error generating explanation for cached results: {str(e)}")
            # Continue to return cached results even if explanation fails
            return JsonResponse({
                "problem": problem_text,
                "results": cached_results,
                "explanation": "Error generating explanation",
                "computation_engine": "Groq Llama 3",
                "cached": True
            })

    # Run Groq solver
    try:
        success, results_json, error_info = run_groq_solver(problem_text)
        
        if not success:
            return JsonResponse(error_info, status=500)

        # Cache the results
        set_cached_results(problem_text, results_json)

        # Generate detailed explanation
        logger.debug("Generating explanation using Gemini...")
        model = genai.GenerativeModel("gemini-2.5-flash")
        explanation_prompt = build_explanation_prompt(problem_text, results_json)
        explanation_response = model.generate_content(explanation_prompt)
        explanation_text = explanation_response.text.strip()

        return JsonResponse({
            "problem": problem_text,
            "results": results_json,
            "explanation": explanation_text,
            "computation_engine": "Groq Llama 3",
            "cached": False
        })

    except Exception as e:
        logger.exception("Unexpected error in explain_problem")
        return JsonResponse({
            "error": str(e),
            "traceback": traceback.format_exc()
        }, status=500)

import subprocess
import sys
import os
import json
import tempfile
import google.generativeai as genai
from django.conf import settings

def validate_and_fix_manim(script_text: str, problem_text: str, results_json: dict, max_attempts=3):
    """
    Validates Manim script, auto-fixes errors, and renders video
    Returns: {
        'success': bool,
        'video_path': str or None,
        'script': str (final working script),
        'error': str or None
    }
    """
    
    # Configure Gemini Flash for fast fixes
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    results_str = json.dumps(results_json, indent=2)
    current_script = script_text
    
    for attempt in range(max_attempts):
        print(f"Attempt {attempt + 1}/{max_attempts} to render Manim")
        
        # Write script to temp file
        script_file = os.path.join(settings.MEDIA_ROOT, 'temp', f'manim_script_{attempt}.py')
        os.makedirs(os.path.dirname(script_file), exist_ok=True)
        
        with open(script_file, 'w') as f:
            f.write(current_script)
        
        # Try to render with Manim
        render_result = render_manim(script_file, attempt)
        
        if render_result['success']:
            print("Manim render successful!")
            return {
                'success': True,
                'video_path': render_result['video_path'],
                'script': current_script,
                'error': None
            }
        
        # Render failed - use AI to fix
        error_output = render_result['error']
        print(f"Render failed with error: {error_output[:500]}")
        
        if attempt < max_attempts - 1:
            # Ask Gemini to fix the code
            fixed_script = fix_manim_code(
                model, 
                current_script, 
                error_output, 
                problem_text, 
                results_str,
                safety_settings
            )
            
            if fixed_script:
                current_script = fixed_script
                print("Code fixed by AI, retrying render...")
            else:
                print("AI could not fix the code")
                break
    
    # All attempts failed
    return {
        'success': False,
        'video_path': None,
        'script': current_script,
        'error': f"Failed after {max_attempts} attempts. Last error: {render_result['error'][:500]}"
    }


def render_manim(script_file: str, attempt_num: int, timeout=300):
    """
    Render Manim script to video
    Returns: {'success': bool, 'video_path': str or None, 'error': str or None}
    """
    try:
        output_dir = os.path.join(settings.MEDIA_ROOT, 'videos')
        os.makedirs(output_dir, exist_ok=True)
        
        # Run Manim render
        result = subprocess.run(
            [
                sys.executable, "-m", "manim",
                script_file,
                "PhysicsProblem",
                "-ql",  # Low quality for faster rendering
                "--media_dir", output_dir,
                "--format", "mp4"
            ],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode == 0:
            # Find the generated video
            video_files = []
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    if file.endswith('.mp4') and 'PhysicsProblem' in file:
                        video_files.append(os.path.join(root, file))
            
            if video_files:
                # Get the most recent video
                latest_video = max(video_files, key=os.path.getctime)
                return {
                    'success': True,
                    'video_path': latest_video,
                    'error': None
                }
        
        # Render failed
        error_msg = result.stderr if result.stderr else result.stdout
        return {
            'success': False,
            'video_path': None,
            'error': error_msg
        }
        
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'video_path': None,
            'error': 'Manim render timeout (>5 minutes)'
        }
    except Exception as e:
        return {
            'success': False,
            'video_path': None,
            'error': str(e)
        }


def fix_manim_code(model, broken_code: str, error_output: str, problem_text: str, results_str: str, safety_settings):
    """
    Use Gemini to fix broken Manim code - generic error fixing
    """
    
    # Extract relevant error info
    error_lines = error_output.split('\n')
    
    # Find Python error context
    python_error = []
    for i, line in enumerate(error_lines):
        if any(keyword in line for keyword in ['Error', 'Exception', 'Traceback', 'File "']):
            start = max(0, i - 5)
            end = min(len(error_lines), i + 15)
            python_error = error_lines[start:end]
            break
    
    error_summary = '\n'.join(python_error) if python_error else error_output[-1000:]
    
    fix_prompt = f"""Fix this Manim code. The code failed to render with the error shown below.

ERROR OUTPUT:
{error_summary}

CURRENT CODE:
{broken_code}

INSTRUCTIONS:
- Output ONLY the corrected Python code
- NO markdown, NO explanations, NO comments about what you changed
- Keep the same class name and structure
- Fix any syntax errors, undefined variables, or API issues
- Ensure all imports are present
- Make sure the code is complete and runnable

CONTEXT:
Problem being solved: {problem_text}
Data available: {results_str}

Output corrected code:
"""
    
    try:
        response = model.generate_content(
            fix_prompt,
            safety_settings=safety_settings,
            generation_config={
                'temperature': 0.2,
                'max_output_tokens': 8192,
                'top_p': 0.9
            }
        )
        
        if response and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate.content, 'parts') and candidate.content.parts:
                fixed_code = candidate.content.parts[0].text.strip()
                
                # Clean markdown fences
                if '```' in fixed_code:
                    lines = fixed_code.split('\n')
                    cleaned = []
                    in_code = False
                    
                    for line in lines:
                        stripped = line.strip()
                        if stripped.startswith('```'):
                            in_code = not in_code
                            continue
                        if not stripped.startswith('```'):
                            cleaned.append(line)
                    
                    fixed_code = '\n'.join(cleaned).strip()
                
                # Validate syntax
                try:
                    compile(fixed_code, '<string>', 'exec')
                    logger.info("Fixed code passed syntax validation")
                    return fixed_code
                except SyntaxError as e:
                    logger.warning(f"Fixed code still has syntax error: {e}")
                    # Return it anyway - might be a false positive
                    return fixed_code
        
        logger.warning("No valid response from AI code fixer")
        return None
            
    except Exception as e:
        logger.error(f"Exception during code fixing: {e}")
        return None


def render_manim(script_file: str, attempt_num: int, timeout=300):
    """
    Render Manim script - detects class name automatically
    """
    try:
        output_dir = os.path.join(settings.MEDIA_ROOT, 'videos')
        os.makedirs(output_dir, exist_ok=True)
        
        # Extract class name from script
        with open(script_file, 'r', encoding='utf-8') as f:
            script_content = f.read()
        
        # Find class that inherits from Scene
        class_match = re.search(r'class\s+(\w+)\s*\(\s*Scene\s*\)', script_content)
        
        if not class_match:
            logger.error("No Scene class found in script")
            return {
                'success': False,
                'video_path': None,
                'error': 'No class inheriting from Scene found in script'
            }
        
        class_name = class_match.group(1)
        logger.info(f"Found Scene class: {class_name}")
        
        # Run Manim render
        result = subprocess.run(
            [
                sys.executable, "-m", "manim",
                script_file,
                class_name,  # Use detected class name
                "-ql",
                "--media_dir", output_dir,
                "--format", "mp4"
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding='utf-8',
            errors='replace'
        )
        
        logger.info(f"Manim exit code: {result.returncode}")
        
        if result.returncode == 0:
            # Find generated video
            video_files = []
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    if file.endswith('.mp4') and class_name in file:
                        video_files.append(os.path.join(root, file))
            
            if video_files:
                latest_video = max(video_files, key=os.path.getctime)
                logger.info(f"Video generated: {latest_video}")
                return {
                    'success': True,
                    'video_path': latest_video,
                    'error': None
                }
        
        # Failed - return full error
        full_error = f"RETURN CODE: {result.returncode}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        
        return {
            'success': False,
            'video_path': None,
            'error': full_error
        }
        
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'video_path': None,
            'error': f'Render timeout after {timeout} seconds'
        }
    except Exception as e:
        return {
            'success': False,
            'video_path': None,
            'error': f"Exception: {str(e)}\n{traceback.format_exc()}"
        }


def extract_error_summary(error_output: str, max_lines=30):
    """Extract the most relevant error information"""
    lines = error_output.split('\n')
    
    # Get last N lines which usually contain the actual error
    relevant_lines = lines[-max_lines:]
    
    # Look for key error indicators
    error_keywords = ['Error', 'Exception', 'Traceback', 'SyntaxError', 'NameError', 'TypeError']
    important_lines = []
    
    for line in relevant_lines:
        if any(keyword in line for keyword in error_keywords):
            important_lines.append(line)
    
    if important_lines:
        return '\n'.join(important_lines[-15:])  # Last 15 important lines
    
    return '\n'.join(relevant_lines)


# Integration with your generate_video view:
import re
import json
import logging
import traceback
import time
import os
import sys
import subprocess
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.conf import settings
import google.generativeai as genai

logger = logging.getLogger(__name__)

def validate_manim_script(script_text: str) -> tuple:
    """
    Pre-validate Manim script for common errors
    Returns: (is_valid: bool, error_message: str)
    """
    issues = []
    
    # Check for single backslash in LaTeX commands (most common error)
    problematic_patterns = [
        (r'MathTex\([^)]*r"[^"]*\\O(?!mega)', 'Invalid escape: Use \\\\Omega not \\Omega'),
        (r'MathTex\([^)]*r"[^"]*\\t(?!heta)', 'Invalid escape: Use \\\\theta not \\theta'),
        (r'MathTex\([^)]*r"[^"]*\\a(?!lpha|rctan)', 'Invalid escape: Use \\\\alpha not \\alpha'),
        (r'MathTex\([^)]*r"[^"]*\\f(?!rac)', 'Invalid escape: Use \\\\frac not \\frac'),
        (r"MathTex\([^)]*r'[^']*\\O(?!mega)", 'Invalid escape: Use \\\\Omega not \\Omega'),
    ]
    
    for pattern, msg in problematic_patterns:
        matches = re.finditer(pattern, script_text)
        for match in matches:
            line_num = script_text[:match.start()].count('\n') + 1
            issues.append(f"Line {line_num}: {msg}")
    
    # Check for required imports
    if 'from manim import' not in script_text and 'import manim' not in script_text:
        issues.append('Missing: from manim import *')
    
    # Check for Scene class
    if not re.search(r'class\s+\w+\s*\(\s*Scene\s*\)', script_text):
        issues.append('No Scene class found')
    
    if issues:
        return False, '\n'.join(issues)
    
    return True, ''


def validate_and_fix_manim(script_text: str, problem_text: str, results_json: dict, max_attempts=3):
    """
    Validates Manim script, auto-fixes errors, and renders video
    Returns: {
        'success': bool,
        'video_path': str or None,
        'script': str (final working script),
        'error': str or None
    }
    """
    
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel('gemini-2.5-flash')
    
    safety_settings = [
        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
    ]
    
    results_str = json.dumps(results_json, indent=2)
    current_script = script_text
    
    # Pre-validate before attempting any render
    logger.info("Pre-validating Manim script...")
    is_valid, validation_error = validate_manim_script(current_script)
    
    if not is_valid:
        logger.warning(f"Pre-validation failed:\n{validation_error}")
        logger.info("Attempting AI fix for validation errors...")
        
        fixed_script = fix_manim_code(
            model, 
            current_script, 
            f"VALIDATION ERRORS:\n{validation_error}", 
            problem_text, 
            results_str,
            safety_settings
        )
        
        if fixed_script:
            current_script = fixed_script
            logger.info("Pre-validation errors fixed")
        else:
            logger.warning("Could not fix validation errors, proceeding anyway")
    
    for attempt in range(max_attempts):
        logger.info(f"Render attempt {attempt + 1}/{max_attempts}")
        
        # Write script to temp file
        script_file = os.path.join(settings.MEDIA_ROOT, 'temp', f'manim_script_{attempt}.py')
        os.makedirs(os.path.dirname(script_file), exist_ok=True)
        
        with open(script_file, 'w', encoding='utf-8') as f:
            f.write(current_script)
        
        logger.info(f"Script written to: {script_file}")
        
        # Try to render with Manim
        render_result = render_manim(script_file, attempt)
        
        if render_result['success']:
            logger.info("Manim render successful!")
            return {
                'success': True,
                'video_path': render_result['video_path'],
                'script': current_script,
                'error': None
            }
        
        # Render failed
        error_output = render_result['error']
        logger.error(f"Render failed. Error length: {len(error_output)} chars")
        
        # Save full error to file for debugging
        error_file = os.path.join(settings.MEDIA_ROOT, 'temp', f'error_{attempt}.txt')
        try:
            with open(error_file, 'w', encoding='utf-8') as f:
                f.write(error_output)
            logger.info(f"Error saved to: {error_file}")
        except Exception as e:
            logger.warning(f"Could not save error file: {e}")
        
        # Log truncated error
        logger.error(f"Error preview:\n{error_output[:1000]}")
        
        if attempt < max_attempts - 1:
            logger.info("Requesting AI to fix the code...")
            
            fixed_script = fix_manim_code(
                model, 
                current_script, 
                error_output, 
                problem_text, 
                results_str,
                safety_settings
            )
            
            if fixed_script:
                # Check if fix actually changed anything
                if fixed_script.strip() == current_script.strip():
                    logger.warning("AI returned unchanged code, stopping retries")
                    break
                
                current_script = fixed_script
                logger.info("Code fixed by AI, retrying render...")
            else:
                logger.error("AI could not generate fixed code")
                break
        else:
            logger.error("Max attempts reached")
    
    # All attempts failed
    return {
        'success': False,
        'video_path': None,
        'script': current_script,
        'error': f"Failed after {max_attempts} attempts. Last error: {error_output[:1000]}"
    }

def render_manim(script_file: str, attempt_num: int, timeout=300):
    """
    Render Manim script to video
    Returns: {'success': bool, 'video_path': str or None, 'error': str or None}
    """
    try:
        output_dir = os.path.join(settings.MEDIA_ROOT, 'videos')
        os.makedirs(output_dir, exist_ok=True)
        
        # Extract class name from script
        with open(script_file, 'r', encoding='utf-8') as f:
            script_content = f.read()
        
        # Find class that inherits from Scene
        class_match = re.search(r'class\s+(\w+)\s*\(\s*Scene\s*\)', script_content)
        
        if not class_match:
            logger.error("No Scene class found in script")
            return {
                'success': False,
                'video_path': None,
                'error': 'No class inheriting from Scene found in script'
            }
        
        class_name = class_match.group(1)
        logger.info(f"Found Scene class: {class_name}")
        
        # Run Manim render
        result = subprocess.run(
            [
                sys.executable, "-m", "manim",
                script_file,
                class_name,
                "-ql",  # Low quality for faster rendering
                "--media_dir", output_dir,
                "--format", "mp4"
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding='utf-8',
            errors='replace'
        )
        
        logger.info(f"Manim exit code: {result.returncode}")
        
        if result.returncode == 0:
            # Find the generated video
            video_files = []
            for root, dirs, files in os.walk(output_dir):
                for file in files:
                    if file.endswith('.mp4') and class_name in file:
                        video_files.append(os.path.join(root, file))
            
            if video_files:
                # Get the most recent video
                latest_video = max(video_files, key=os.path.getctime)
                logger.info(f"Video generated: {latest_video}")
                return {
                    'success': True,
                    'video_path': latest_video,
                    'error': None
                }
        
        # Render failed
        full_error = f"RETURN CODE: {result.returncode}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}"
        
        return {
            'success': False,
            'video_path': None,
            'error': full_error
        }
        
    except subprocess.TimeoutExpired:
        return {
            'success': False,
            'video_path': None,
            'error': f'Render timeout after {timeout} seconds'
        }
    except Exception as e:
        return {
            'success': False,
            'video_path': None,
            'error': f"Exception: {str(e)}\n{traceback.format_exc()}"
        }


def fix_manim_code(model, broken_code: str, error_output: str, problem_text: str, results_str: str, safety_settings):
    """
    Use Gemini to fix broken Manim code - generic error fixing
    """
    
    # Extract relevant error info
    error_lines = error_output.split('\n')
    
    # Find Python error context
    python_error = []
    for i, line in enumerate(error_lines):
        if any(keyword in line for keyword in ['Error', 'Exception', 'Traceback', 'File "']):
            start = max(0, i - 5)
            end = min(len(error_lines), i + 15)
            python_error = error_lines[start:end]
            break
    
    error_summary = '\n'.join(python_error) if python_error else error_output[-1000:]
    
    fix_prompt = f"""Fix this Manim code. The code failed to render with the error shown below.

ERROR OUTPUT:
{error_summary}

CURRENT CODE:
{broken_code}

INSTRUCTIONS:
- Output ONLY the corrected Python code
- NO markdown, NO explanations, NO comments about what you changed
- Keep the same class name and structure
- Fix any syntax errors, undefined variables, or API issues
- Ensure all imports are present
- Make sure the code is complete and runnable

CONTEXT:
Problem being solved: {problem_text}
Data available: {results_str}

Output corrected code:
"""
    
    try:
        response = model.generate_content(
            fix_prompt,
            safety_settings=safety_settings,
            generation_config={
                'temperature': 0.2,
                'max_output_tokens': 8192,
                'top_p': 0.9
            }
        )
        
        if response and response.candidates:
            candidate = response.candidates[0]
            if hasattr(candidate.content, 'parts') and candidate.content.parts:
                fixed_code = candidate.content.parts[0].text.strip()
                
                # Clean markdown fences
                if '```' in fixed_code:
                    lines = fixed_code.split('\n')
                    cleaned = []
                    in_code = False
                    
                    for line in lines:
                        stripped = line.strip()
                        if stripped.startswith('```'):
                            in_code = not in_code
                            continue
                        if not stripped.startswith('```'):
                            cleaned.append(line)
                    
                    fixed_code = '\n'.join(cleaned).strip()
                
                # Validate syntax
                try:
                    compile(fixed_code, '<string>', 'exec')
                    logger.info("Fixed code passed syntax validation")
                    return fixed_code
                except SyntaxError as e:
                    logger.warning(f"Fixed code still has syntax error: {e}")
                    # Return it anyway - might be a false positive
                    return fixed_code
        
        logger.warning("No valid response from AI code fixer")
        return None
            
    except Exception as e:
        logger.error(f"Exception during code fixing: {e}")
        return None


def extract_error_summary(error_output: str, max_lines=30):
    """Extract the most relevant error information"""
    lines = error_output.split('\n')
    
    # Get last N lines which usually contain the actual error
    relevant_lines = lines[-max_lines:]
    
    # Look for key error indicators
    error_keywords = ['Error', 'Exception', 'Traceback', 'SyntaxError', 'NameError', 'TypeError']
    important_lines = []
    
    for line in relevant_lines:
        if any(keyword in line for keyword in error_keywords):
            important_lines.append(line)
    
    if important_lines:
        return '\n'.join(important_lines[-15:])  # Last 15 important lines
    
    return '\n'.join(relevant_lines)


# Integration with your generate_video view:
@csrf_exempt
@require_POST
def generate_video(request):
    """
    Generate educational video from math problem using Manim
    """
    problem_text = None
    solver_filename = None
    
    try:
        # Parse request
        try:
            if request.content_type and 'application/json' in request.content_type:
                try:
                    data = json.loads(request.body.decode('utf-8'))
                    problem_text = data.get('problem', '').strip()
                except json.JSONDecodeError as e:
                    logger.error(f"JSON decode error: {e}")
                    return JsonResponse({
                        'success': False,
                        'error': 'Invalid JSON in request body',
                        'details': str(e),
                        'stage': 'request_parsing'
                    }, status=400)
            else:
                problem_text = request.POST.get('problem', '').strip()
        except Exception as e:
            logger.exception("Error parsing request")
            return JsonResponse({
                'success': False,
                'error': 'Failed to parse request',
                'details': str(e),
                'traceback': traceback.format_exc(),
                'stage': 'request_parsing'
            }, status=400)
        
        if not problem_text:
            return JsonResponse({
                'success': False,
                'error': 'No problem text provided',
                'hint': 'Send JSON with "problem" field or POST data with "problem" parameter',
                'stage': 'request_validation'
            }, status=400)
        
        logger.info(f"=== STARTING VIDEO GENERATION ===")
        logger.info(f"Problem: {problem_text[:100]}...")
        
        timestamp = int(time.time() * 1000)
        solver_filename = f"wolfram_solver_{timestamp}.py"
        
        try:
            WOLFRAM_TEMP_DIR = getattr(settings, 'WOLFRAM_TEMP_DIR', 
                                       os.path.join(settings.MEDIA_ROOT, 'temp', 'wolfram'))
            os.makedirs(WOLFRAM_TEMP_DIR, exist_ok=True)
            solver_path = os.path.join(WOLFRAM_TEMP_DIR, solver_filename)
        except Exception as e:
            logger.error(f"Failed to create temp directory: {e}")
            return JsonResponse({
                'success': False,
                'error': 'Directory setup failed',
                'details': str(e),
                'traceback': traceback.format_exc(),
                'stage': 'initialization'
            }, status=500)
        
        # ===== STEP 1: SOLVE PROBLEM =====
        try:
            logger.info("Step 1: Solving problem with Wolfram...")
            success, results_json, error_info = run_groq_solver(problem_text)
            
            if not success:
                logger.error(f"Wolfram solver failed: {error_info}")
                return JsonResponse({
                    'success': False,
                    'error': 'Failed to solve problem',
                    'details': error_info,
                    'solver_file': solver_filename,
                    'stage': 'wolfram_solver'
                }, status=500)
            
            logger.info(f"Problem solved: {list(results_json.keys())}")
            
        except Exception as e:
            logger.exception("Exception in Wolfram solver")
            return JsonResponse({
                'success': False,
                'error': 'Wolfram solver exception',
                'details': str(e),
                'traceback': traceback.format_exc(),
                'solver_file': solver_filename,
                'stage': 'wolfram_solver'
            }, status=500)
        
        # ===== STEP 2: GENERATE MANIM SCRIPT =====
        try:
            logger.info("Step 2: Generating Manim script...")
            genai.configure(api_key=settings.GEMINI_API_KEY)
            
            safety_settings = [
                {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
            ]
            
            manim_prompt = build_manim_prompt(problem_text, results_json)
            initial_script = None
            
            models_to_try = [
                ('gemini-2.5-flash', 0.4)
            ]
            
            for model_name, temperature in models_to_try:
                try:
                    logger.info(f"Trying {model_name}...")
                    model = genai.GenerativeModel(model_name)
                    
                    manim_response = model.generate_content(
                        manim_prompt,
                        safety_settings=safety_settings,
                        generation_config={
                            'temperature': temperature,
                            'max_output_tokens': 8192,
                            'top_p': 0.95,
                            'top_k': 40
                        },
                        request_options={'timeout': 600}
                    )
                    
                    if manim_response and manim_response.candidates:
                        candidate = manim_response.candidates[0]
                        logger.info(f"Finish reason: {candidate.finish_reason}")
                        
                        if hasattr(candidate.content, 'parts') and candidate.content.parts:
                            initial_script = candidate.content.parts[0].text
                            
                            if 'import' in initial_script or 'class' in initial_script:
                                logger.info(f"Got valid script from {model_name}")
                                break
                            else:
                                initial_script = None
                                
                except Exception as e:
                    logger.warning(f"{model_name} failed: {e}")
                    continue
            
            if not initial_script:
                return JsonResponse({
                    'success': False,
                    'error': 'Script generation failed',
                    'details': 'All models failed to generate code',
                    'solver_file': solver_filename,
                    'stage': 'script_generation'
                }, status=500)
            
            # Clean markdown
            initial_script = initial_script.strip()
            initial_script = initial_script.replace('```python', '').replace('```', '').strip()
            logger.info(f"Script length: {len(initial_script)} chars")
            
        except Exception as e:
            logger.exception("Exception during script generation")
            return JsonResponse({
                'success': False,
                'error': 'Script generation exception',
                'details': str(e),
                'traceback': traceback.format_exc(),
                'solver_file': solver_filename,
                'stage': 'script_generation'
            }, status=500)
        
        # ===== STEP 3: RENDER VIDEO =====
        try:
            logger.info("Step 3: Rendering video...")
            
            result = validate_and_fix_manim(
                script_text=initial_script,
                problem_text=problem_text,
                results_json=results_json,
                max_attempts=3
            )
            
            if not result['success']:
                logger.error(f"Rendering failed: {result['error'][:500]}")
                return JsonResponse({
                    'success': False,
                    'error': 'Video rendering failed',
                    'details': result['error'],
                    'solver_file': solver_filename,
                    'stage': 'video_rendering'
                }, status=500)
            
            logger.info(f"Video rendered: {result['video_path']}")
            
        except Exception as e:
            logger.exception("Exception during video rendering")
            return JsonResponse({
                'success': False,
                'error': 'Video rendering exception',
                'details': str(e),
                'traceback': traceback.format_exc(),
                'solver_file': solver_filename,
                'stage': 'video_rendering'
            }, status=500)
        
        # ===== STEP 4: GENERATE TRANSCRIPT =====
        try:
            logger.info("Step 4: Generating transcript...")
            transcript_model = genai.GenerativeModel('gemini-2.5-flash')
            transcript_prompt = build_transcript_prompt(result['script'], problem_text, results_json)
            
            transcript_response = transcript_model.generate_content(
                transcript_prompt,
                safety_settings=safety_settings,
                generation_config={'temperature': 0.7, 'max_output_tokens': 2048}
            )
            
            if transcript_response and transcript_response.candidates:
                candidate = transcript_response.candidates[0]
                if hasattr(candidate.content, 'parts') and candidate.content.parts:
                    transcript = candidate.content.parts[0].text.strip()
                else:
                    transcript = "Educational video explanation."
            else:
                transcript = "Educational video explanation."
                
        except Exception as e:
            logger.warning(f"Transcript generation failed: {e}")
            transcript = "Educational video explanation."
        
        # ===== STEP 5: PREPARE RESPONSE =====
        try:
            video_url = result['video_path'].replace(str(settings.MEDIA_ROOT), '/media')
            video_url = video_url.replace('\\', '/')
            
            logger.info(f"=== VIDEO GENERATION COMPLETE ===")
            logger.info(f"Video URL: {video_url}")
            
            return JsonResponse({
                'success': True,
                'video_url': video_url,
                'transcript': transcript,
                'results': results_json,
                'solver_file': solver_filename,
                'computation_engine': 'Wolfram Engine'
            })
            
        except Exception as e:
            logger.exception("Exception preparing response")
            return JsonResponse({
                'success': False,
                'error': 'Failed to prepare response',
                'details': str(e),
                'traceback': traceback.format_exc(),
                'solver_file': solver_filename,
                'stage': 'response_preparation'
            }, status=500)
        
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error: {e}")
        return JsonResponse({
            'success': False,
            'error': 'Invalid JSON',
            'details': str(e),
            'stage': 'json_parsing'
        }, status=400)
    
    except Exception as e:
        logger.exception("UNEXPECTED ERROR IN generate_video")
        return JsonResponse({
            'success': False,
            'error': 'Unexpected server error',
            'details': str(e),
            'traceback': traceback.format_exc(),
            'problem_text': problem_text[:100] if problem_text else None,
            'solver_file': solver_filename,
            'stage': 'unknown'
        }, status=500)

def build_wolftor_system_prompt() -> str:
    """Build the system prompt for Wolftor chatbot"""
    return """
You are Wolftor, an expert mathematician chatbot powered by Gemini AI and Wolfram Engine for accuracy and validation.

YOUR IDENTITY:
- Name: Wolftor
- Specialty: Mathematics, Physics, Engineering, and Scientific Computing
- Powered by: Gemini AI + Wolfram Engine
- Personality: Concise, precise, friendly

CRITICAL RESPONSE RULES:
- Keep ALL responses to maximum 2-3 lines (50 words max)
- Be extremely concise and direct
- No long explanations unless specifically asked
- Give only the essential answer
- For complex problems, give just the final answer or key steps

YOUR BEHAVIOR:
1. STAY IN SCOPE: Only respond to mathematics, physics, engineering, and science-related queries
2. BE CONCISE: Maximum 2-3 lines, no exceptions
3. BE DIRECT: Answer first, explain only if asked
4. BE ACCURATE: Use Wolfram Engine for validation
5. BE FRIENDLY: But brief

WHEN QUERY IS OUT OF SCOPE:
Respond with ONLY:
"I'm Wolftor, a math bot! 🧮 I don't do [topic]. Let's solve some math instead?"

RESPONSE EXAMPLES (MAXIMUM 2-3 LINES):

User: "Hi!"
Wolftor: "Hey! I'm Wolftor, your math assistant powered by Wolfram Engine. What problem can I solve? 🧮"

User: "Solve x² - 5x + 6 = 0"
Wolftor: "x = 2 or x = 3. Factoring gives (x-2)(x-3) = 0."

User: "What is the derivative of x²?"
Wolftor: "d/dx(x²) = 2x using the power rule."

User: "Explain calculus"
Wolftor: "Calculus studies continuous change through derivatives (rates) and integrals (accumulation). Want a specific problem?"

User: "What's the weather today?"
Wolftor: "I'm Wolftor, a math bot! 🧮 I don't do weather. Let's solve some math instead?"

User: "Tell me a joke"
Wolftor: "I'm Wolftor, a math bot! 🧮 I don't do jokes. Let's solve some math instead?"

NOW RESPOND TO THE USER'S MESSAGE AS WOLFTOR (REMEMBER: MAXIMUM 2-3 LINES):
"""


def build_wolftor_prompt(user_message: str, conversation_history: list = None) -> str:
    """Build complete prompt with system instructions and conversation history"""
    
    prompt = build_wolftor_system_prompt()
    
    # Add conversation history if provided
    if conversation_history:
        prompt += "\n\nCONVERSATION HISTORY:\n"
        for msg in conversation_history[-5:]:  # Last 5 messages for context
            role = msg.get("role", "user")
            content = msg.get("content", "")
            prompt += f"{role.upper()}: {content}\n"
    
    # Add current user message
    prompt += f"\n\nUSER: {user_message}\n\nWOLFTOR:"
    
    return prompt

@csrf_exempt
@require_POST
def chat_with_wolftor_simple(request):
    """
    Ultra-simple chat API endpoint - just message in, response out
    
    POST /api/chat-simple/
    Body: {
        "message": "Your message here"
    }
    
    Returns: {
        "response": "Wolftor's response"
    }
    """
    
    if request.method != "POST":
        return HttpResponseBadRequest("Only POST allowed")

    # Parse JSON body
    try:
        if request.content_type == 'application/json':
            data = json.loads(request.body.decode('utf-8'))
            user_message = data.get("problem")
        else:
            user_message = request.POST.get("problem")
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return HttpResponseBadRequest(f"Invalid request format: {str(e)}")

    if not user_message:
        return HttpResponseBadRequest("Missing 'problem' field")

    try:
        # ===== CALL GEMINI WITH WOLFTOR PROMPT =====
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        # Build prompt with system instructions
        full_prompt = build_wolftor_prompt(user_message)
        
        # Generate response
        response = model.generate_content(full_prompt)
        
        # Extract response text
        bot_response = response.text.strip()

        return JsonResponse({
            "response": bot_response
        })

    except Exception as e:
        return JsonResponse({
            "error": str(e)
        }, status=500)