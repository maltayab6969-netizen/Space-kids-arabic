# -*- coding: utf-8 -*-
"""
Space Kids Arabic Studio
أداة محلية لإنشاء حزمة فيديو يوتيوب للأطفال: سيناريو + أوصاف صور + صور + صوت + تصدير منظم.

تشغيل سريع:
    pip install -r requirements.txt
    streamlit run app.py

الخدمات الاختيارية:
- Ollama محلي: http://localhost:11434 (لا يحتاج مفتاحًا)
- Pollinations للنص/الصور: ضع POLLINATIONS_API_KEY في البيئة
- أي مزود OpenAI-compatible: ضع OPENAI_API_KEY و OPENAI_API_BASE و OPENAI_MODEL
"""

from __future__ import annotations

import io
import json
import os
import re
import textwrap
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests
import streamlit as st

APP_TITLE = "استوديو سبيس كيدز العربية"
DEFAULT_OUTPUT = Path.home() / "SpaceKidsArabic_Projects"
POLLINATIONS_BASE = "https://gen.pollinations.ai"
LEGACY_IMAGE_BASE = "https://image.pollinations.ai/prompt"


def slugify(value: str) -> str:
    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE).strip()
    value = re.sub(r"[\s_-]+", "_", value)
    return value[:70] or "مشروع_جديد"


def clean_json_text(raw: str) -> dict:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start >= 0 and end > start:
        raw = raw[start : end + 1]
    return json.loads(raw)


def project_prompt(idea: str, age: str, scenes: int, style: str) -> str:
    return f"""
أنت كاتب ومخرج محتوى أطفال عربي لقناة يوتيوب اسمها سبيس كيدز العربية.
اكتب قصة أصلية آمنة ومبهجة للأطفال بعمر {age}، فكرتها: {idea}
عدد المشاهد المطلوب: {scenes}. الأسلوب البصري: {style}.
تجنب العنف والخوف الشديد والمعلومات الخطرة والعلامات التجارية والشخصيات المحمية.
اجعل اللغة العربية فصحى مبسطة، والجمل مناسبة للتعليق الصوتي.
مهم جدًا: أعد JSON صالحًا فقط بلا Markdown، بهذا الشكل:
{{
  "title": "عنوان جذاب",
  "logline": "ملخص من جملة واحدة",
  "lesson": "القيمة التعليمية",
  "characters": [
    {{"name":"...", "description":"وصف ثابت شامل للعمر والملابس والألوان والملامح"}}
  ],
  "scenes": [
    {{
      "number": 1,
      "section": "مقدمة|أحداث|خاتمة",
      "title": "عنوان المشهد",
      "duration_seconds": 10,
      "narration": "نص التعليق الصوتي بالعربية، من 2 إلى 5 جمل",
      "action": "ما يحدث بصريًا",
      "image_prompt": "وصف صورة باللغة الإنجليزية، أفقي 16:9، يتضمن الشخصيات واتساقها والمكان والإضاءة، بلا نص داخل الصورة"
    }}
  ]
}}
يجب أن يكون عدد عناصر scenes مساويًا تمامًا لـ {scenes}.
""".strip()


def fallback_story(idea: str, scenes: int, age: str, style: str) -> dict:
    chars = [
        {"name": "لومي", "description": "طفلة عربية فضولية عمرها 8 سنوات، شعر بني مجعد مربوط بربطة زرقاء، بدلة فضاء بنفسجية ونجمة صفراء على الصدر، حذاء أبيض، ملامح لطيفة وابتسامة دافئة."},
        {"name": "نونو", "description": "روبوت كروي صغير أزرق وفضي، عينان دائريتان مضيئتان باللون السماوي، ذراعان قصيران، لطيف ومرح."},
    ]
    beats = [
        ("مقدمة", "رسالة غامضة من النجوم", "في ليلة هادئة، تلمع نجمة صغيرة قرب نافذة لومي وتدعوها إلى مغامرة لطيفة.", "Lumi and Nono discover a friendly glowing star message near a bedroom window, colorful 3D animated family-film look, warm moonlight, wide shot, no text"),
        ("أحداث", "الطريق إلى الكوكب الملون", "تنطلق لومي ونونو بمركبتهما الصغيرة، ويتعلمان أن التعاون يجعل الطريق أسهل وأجمل.", "Lumi and Nono travel in a tiny colorful spaceship toward a rainbow planet, same character design and outfits, joyful space clouds, cinematic 3D animation, wide 16:9, no text"),
        ("خاتمة", "هدية من الفضاء", "يكتشف الصديقان أن الهدية الحقيقية هي مساعدة الآخرين، ويعودان بابتسامة ووعد بمغامرة جديدة.", "Lumi and Nono help tiny friendly star creatures in a bright garden on a rainbow planet, same character design, golden sunrise, joyful cinematic 3D animation, wide 16:9, no text"),
    ]
    while len(beats) < scenes:
        i = len(beats) + 1
        beats.insert(-1, ("أحداث", f"مفاجأة رقم {i}", f"تواجه لومي ونونو موقفًا صغيرًا حول {idea}، ثم يجدان حلًا ذكيًا بالتعاون.", f"Lumi and Nono solve a gentle child-friendly challenge about {idea}, same consistent characters, colorful 3D animated family-film look, wide 16:9, no text"))
    beats = beats[:scenes]
    return {
        "title": idea[:70],
        "logline": f"مغامرة لطيفة حول {idea} يتعلم فيها الأصدقاء قيمة التعاون.",
        "lesson": "التعاون والفضول وحسن مساعدة الآخرين.",
        "characters": chars,
        "scenes": [
            {"number": i + 1, "section": b[0], "title": b[1], "duration_seconds": 12, "narration": b[2], "action": b[2], "image_prompt": b[3]}
            for i, b in enumerate(beats)
        ],
    }


def call_ollama(prompt: str, model: str) -> str:
    response = requests.post(
        os.getenv("OLLAMA_URL", "http://localhost:11434/api/chat"),
        json={"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False, "format": "json"},
        timeout=180,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]


def call_openai_compatible(prompt: str) -> str:
    base = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/")
    key = os.getenv("OPENAI_API_KEY", "")
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    response = requests.post(
        f"{base}/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}], "temperature": 0.8},
        timeout=180,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def call_pollinations_text(prompt: str) -> str:
    key = os.getenv("POLLINATIONS_API_KEY", "")
    if not key:
        raise RuntimeError("لم يتم وضع POLLINATIONS_API_KEY")
    response = requests.post(
        f"{POLLINATIONS_BASE}/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        json={"model": os.getenv("POLLINATIONS_TEXT_MODEL", "openai/gpt-5.4-nano"), "messages": [{"role": "user", "content": prompt}]},
        timeout=180,
    )
    response.raise_for_status()
    return response.json()["choices"][0]["message"]["content"]


def generate_story(idea: str, age: str, scenes: int, style: str, provider: str, model: str) -> tuple[dict, str]:
    prompt = project_prompt(idea, age, scenes, style)
    if provider == "Ollama محلي":
        raw = call_ollama(prompt, model)
        return clean_json_text(raw), "Ollama محلي"
    if provider == "Pollinations":
        raw = call_pollinations_text(prompt)
        return clean_json_text(raw), "Pollinations"
    if provider == "OpenAI-compatible":
        raw = call_openai_compatible(prompt)
        return clean_json_text(raw), "OpenAI-compatible"
    return fallback_story(idea, scenes, age, style), "قالب احتياطي بدون API"


def consistent_prompt(character_bible: str, scene: dict, style: str) -> str:
    return (
        f"{scene.get('image_prompt', '')}. {style}. "
        f"Character bible: {character_bible}. Keep faces, clothing, colors, proportions, and accessories identical in every scene. "
        "High detail, child-safe, expressive, polished 3D animated family-film illustration, cinematic lighting, horizontal 16:9, no logos, no watermark, no readable text."
    )


def download_image(prompt: str, path: Path, seed: int, api_key: str = "") -> tuple[bool, str]:
    encoded = quote(prompt, safe="")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    urls = []
    if api_key:
        urls.append(f"{POLLINATIONS_BASE}/image/{encoded}?model=black-forest-labs/flux.1-schnell&width=1280&height=720&seed={seed}&nologo=true")
    urls.append(f"{LEGACY_IMAGE_BASE}/{encoded}?width=1280&height=720&seed={seed}&nologo=true")
    last_error = ""
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=180)
            r.raise_for_status()
            if r.content[:4] == b"\x89PNG" or r.headers.get("content-type", "").startswith("image"):
                path.write_bytes(r.content)
                return True, url
            last_error = f"استجابة ليست صورة: {r.status_code}"
        except Exception as exc:
            last_error = str(exc)
    return False, last_error


def make_audio(text: str, path: Path, voice: str) -> tuple[bool, str]:
    try:
        import asyncio
        import edge_tts
        async def run():
            await edge_tts.Communicate(text, voice=voice, rate="-5%", pitch="+0Hz").save(str(path))
        asyncio.run(run())
        return True, "edge-tts"
    except Exception as exc:
        path.with_suffix(".txt").write_text(text, encoding="utf-8")
        return False, str(exc)


def write_project(story: dict, root: Path, image_enabled: bool, audio_enabled: bool, voice: str, progress) -> list[str]:
    root.mkdir(parents=True, exist_ok=True)
    scenes_dir = root / "scenes"
    scenes_dir.mkdir(exist_ok=True)
    character_bible = " | ".join(f"{c['name']}: {c['description']}" for c in story.get("characters", []))
    style = "cinematic 3D animated family-film look"
    story["character_bible"] = character_bible
    (root / "story.json").write_text(json.dumps(story, ensure_ascii=False, indent=2), encoding="utf-8")
    md = [f"# {story.get('title', 'قصة جديدة')}", "", f"**الملخص:** {story.get('logline', '')}", f"**الدرس:** {story.get('lesson', '')}", "", "## دليل الشخصيات", ""]
    md += [f"- **{c['name']}:** {c['description']}" for c in story.get("characters", [])]
    md += ["", "## المشاهد", ""]
    for scene in story.get("scenes", []):
        n = int(scene.get("number", 1))
        folder = scenes_dir / f"scene_{n:02d}"
        folder.mkdir(exist_ok=True)
        prompt = consistent_prompt(character_bible, scene, style)
        (folder / "image_prompt.txt").write_text(prompt, encoding="utf-8")
        (folder / "narration.txt").write_text(scene.get("narration", ""), encoding="utf-8")
        (folder / "scene.json").write_text(json.dumps(scene, ensure_ascii=False, indent=2), encoding="utf-8")
        if image_enabled:
            progress(f"توليد صورة المشهد {n}...")
            ok, info = download_image(prompt, folder / "image.png", seed=1000 + n, api_key=os.getenv("POLLINATIONS_API_KEY", ""))
            (folder / "image_status.txt").write_text("نجح: " + info if ok else "فشل: " + info, encoding="utf-8")
        if audio_enabled:
            progress(f"توليد صوت المشهد {n}...")
            ok, info = make_audio(scene.get("narration", ""), folder / "voice.mp3", voice)
            (folder / "audio_status.txt").write_text("نجح: " + info if ok else "فشل: " + info, encoding="utf-8")
        md += [f"### المشهد {n}: {scene.get('title', '')}", f"**القسم:** {scene.get('section', '')}", f"**المدة:** {scene.get('duration_seconds', 10)} ثانية", "", scene.get("narration", ""), "", f"**الفعل البصري:** {scene.get('action', '')}", ""]
    (root / "script.md").write_text("\n".join(md), encoding="utf-8")
    readme = """هذه الحزمة مرتبة للمونتاج. كل مشهد داخل مجلد مستقل ويحتوي على النص والصورة والصوت عند نجاح التوليد.

الترتيب المقترح في برنامج المونتاج: scene_01 ثم scene_02 ثم بقية المجلدات.
راجع الصور والصوت قبل النشر، وتأكد من حقوق الاستخدام وشروط الخدمات الخارجية.
"""
    (root / "README.txt").write_text(readme, encoding="utf-8")
    return ["story.json", "script.md", "README.txt"]


def zip_project(root: Path) -> Path:
    zip_path = root.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in root.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(root.parent))
    return zip_path


def main():
    st.set_page_config(page_title=APP_TITLE, page_icon="🌌", layout="wide")
    st.markdown("<style>body{direction:rtl}.stButton button{width:100%;font-weight:700}.small{color:#777}</style>", unsafe_allow_html=True)
    st.title("🌌 استوديو سبيس كيدز العربية")
    st.caption("أنشئ سيناريو أطفالًا، أوصافًا ثابتة للشخصيات، صورًا، تعليقًا صوتيًا، وحزمة جاهزة للمونتاج.")

    with st.sidebar:
        st.header("إعدادات المشروع")
        provider = st.selectbox("مصدر كتابة السيناريو", ["قالب احتياطي بدون API", "Ollama محلي", "Pollinations", "OpenAI-compatible"])
        model = st.text_input("اسم نموذج Ollama عند اختياره", value="llama3.2")
        age = st.selectbox("الفئة العمرية", ["4–6 سنوات", "6–9 سنوات", "9–12 سنة"])
        scenes = st.slider("عدد المشاهد", 3, 12, 5)
        voice = st.selectbox("الصوت العربي", ["ar-EG-SalmaNeural", "ar-EG-ShakirNeural", "ar-AE-FatimaNeural", "ar-SA-ZariyahNeural"])
        image_enabled = st.checkbox("توليد الصور تلقائيًا", value=True)
        audio_enabled = st.checkbox("توليد التعليق الصوتي تلقائيًا", value=True)
        output_base = st.text_input("مجلد الحفظ", value=str(DEFAULT_OUTPUT))
        st.info("لـ Pollinations: ضع POLLINATIONS_API_KEY قبل التشغيل. للصور فقط، سيُجرّب المسار الاحتياطي عند غياب المفتاح.")

    idea = st.text_area("فكرة القصة أو عنوانها", placeholder="مثال: لومي تكتشف لماذا تتغير ألوان القمر وتساعد صديقًا صغيرًا", height=120)
    style = st.text_input("التوجيه البصري العام", value="رسوم ثلاثية الأبعاد سينمائية دافئة مناسبة للأطفال، ألوان زاهية، تعبيرات لطيفة")
    if st.button("إنشاء حزمة الحلقة", type="primary", disabled=not idea.strip()):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        root = Path(output_base).expanduser() / f"{timestamp}_{slugify(idea)}"
        status = st.empty()
        bar = st.progress(0)
        try:
            status.info("جاري كتابة السيناريو وتقسيمه إلى مشاهد...")
            story, source = generate_story(idea.strip(), age, scenes, style, provider, model)
            story["generated_at"] = datetime.now().isoformat(timespec="seconds")
            story["generation_source"] = source
            total = max(1, len(story.get("scenes", [])))
            count = {"n": 0}
            def progress(message: str):
                count["n"] += 1
                status.info(message)
                bar.progress(min(0.98, count["n"] / (total * 2 + 1)))
            write_project(story, root, image_enabled, audio_enabled, voice, progress)
            zip_path = zip_project(root)
            bar.progress(1.0)
            status.success(f"تم الحفظ في: {root}")
            st.subheader(story.get("title", "القصة"))
            st.write(story.get("logline", ""))
            st.write(f"**المصدر:** {source} — **الدرس:** {story.get('lesson', '')}")
            with st.expander("معاينة دليل الشخصيات"):
                for c in story.get("characters", []):
                    st.markdown(f"**{c['name']}**: {c['description']}")
            with st.expander("معاينة المشاهد"):
                for s in story.get("scenes", []):
                    st.markdown(f"**{s.get('number')}. {s.get('title')}** — {s.get('section')}\n\n{s.get('narration')}")
            st.download_button("تنزيل ملف ZIP للحزمة", data=zip_path.read_bytes(), file_name=zip_path.name, mime="application/zip")
        except Exception as exc:
            st.error(f"تعذر إكمال العملية: {exc}")
            st.info("جرّب مصدر القالب الاحتياطي، أو تأكد من تشغيل Ollama/وضع مفاتيح الخدمات في البيئة.")

    st.divider()
    st.markdown("**ملاحظة:** لا أستخدم اسم أو شخصيات محمية داخل التوليد؛ التوجيه البصري في الأداة هو رسوم ثلاثية الأبعاد سينمائية أصلية مناسبة للأطفال.")


if __name__ == "__main__":
    main()
