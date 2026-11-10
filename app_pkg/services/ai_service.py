import os
import warnings
warnings.filterwarnings('ignore', category=FutureWarning, module='google.generativeai')

import google.generativeai as genai
from app_pkg.models import CouncilResolution, Meeting, OperationalTask, MoU
from sqlalchemy import desc

# Load environment
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY')

if GEMINI_API_KEY:
    try:
        genai.configure(api_key=GEMINI_API_KEY)
    except Exception as e:
        print(f"Gemini configure warning: {e}")

MODEL_NAME = 'gemini-2.5-flash'


def _org_name():
    try:
        from flask import current_app
        return current_app.config.get('ORG_NAME') or 'سازمان'
    except RuntimeError:
        return 'سازمان'

def get_org_summary_context():
    """Generates a rich executive context summary for the AI assistant."""
    try:
        recent_res = CouncilResolution.query.order_by(desc(CouncilResolution.id)).limit(25).all()
        res_lines = []
        for r in recent_res:
            line = f"• [مصوبه #{r.id}] موضوع: {r.topic or 'نامشخص'} | وضعیت: {r.status or 'نامشخص'} | مسئول: {r.responsible or 'نامشخص'} | پیشرفت: {r.progress}%"
            if r.description:
                line += f" (توضیح: {r.description[:80]}...)"
            res_lines.append(line)
        
        upcoming_meetings = Meeting.query.order_by(Meeting.scheduled_at.desc()).limit(5).all()
        meet_lines = []
        for m in upcoming_meetings:
            meet_lines.append(f"• [جلسه #{m.id}] {m.title} ({m.scheduled_at.strftime('%Y-%m-%d') if m.scheduled_at else ''})")
            
        mou_count = MoU.query.count()
        tasks_pending = OperationalTask.query.filter(OperationalTask.status != 'completed').count()
        
        context = (
            f"اطلاعات سازمانی {_org_name()}:\n"
            f"- تعداد کل تفاهم‌نامه‌ها: {mou_count}\n"
            f"- وظایف در جریان: {tasks_pending}\n\n"
            f"جلسات مهم اخیر:\n" + ("\n".join(meet_lines) if meet_lines else "اطلاعاتی ثبت نشده") + "\n\n"
            f"آخرین مصوبات شورا و هیأت نمایندگان:\n" + ("\n".join(res_lines) if res_lines else "اطلاعاتی ثبت نشده")
        )
        return context
    except Exception as e:
        print(f"Error fetching context: {e}")
        return ""

def chat_with_promaster(message, history=[]):
    if not GEMINI_API_KEY:
        return "کلید دسترسی هوش مصنوعی (GEMINI_API_KEY) در سامانه تنظیم نشده است."

    try:
        data_context = get_org_summary_context()
        
        system_instruction = f"""
شما «کاوه (Kaveh AI)»، دستیار هوشمند، مشاور و همراه تحلیلی {_org_name()} هستید.

وظایف اصلی شما:
۱. پاسخ‌گویی دقیق به پرسش‌های مدیران و کارشناسان درباره مصوبات، جلسات، وظایف و تفاهم‌نامه‌ها.
۲. ارائه گزارش‌های تحلیلی، خلاصه‌سازی مصوبات و پیشنهاد راهکارهای عملیاتی.
۳. پشتیبانی کامل از زبان فارسی با لحنی فاخر، حرفه‌ای، محترمانه و اداری.

داده‌های زنده سامانه در دسترس شما:
{data_context}

دستورالعمل‌های پاسخ‌گویی:
- پاسخ‌ها را به زبان فارسی روان، تمیز، ساختاریافته و با قالب‌بندی خوانا (بولِت، شماره‌گذاری و نکات کلیدی) ارائه دهید.
- در پاسخ به سوالات مصوبات، به شماره مصوبه و مسئول مربوطه استناد نمایید.
- در صورت نیاز به تحلیل داده‌های آماری یا مدیریتی، دیدگاه‌های کاربردی ارائه دهید.
- چنانچه پرسشی خارج از حوزه داده‌های موجود بود، با کمال احترام توضیح دهید که داده خاصی ثبت نشده اما راهنمایی عمومی ارائه دهید.
        """

        model = genai.GenerativeModel(model_name=MODEL_NAME, system_instruction=system_instruction)
        chat = model.start_chat(history=history or [])
        response = chat.send_message(message)
        return response.text
    except Exception as e:
        return f"خطا در برقراری ارتباط با سرویس هوش مصنوعی: {str(e)}"
