# -*- coding: utf-8 -*-
"""
قراءة الخريطة الشخصية - V4.9 Railway Final

ما الجديد في V1.2:
- لم يعد التطبيق محصورًا بعدد قليل من الدول.
- يستخدم geonamescache لجلب دول ومدن العالم تقريبًا.
- المستخدم يختار الدولة ثم يكتب اسم المدينة.
- خط العرض وخط الطول وفرق التوقيت تبقى مخفية عن القارئ.
- الساعة بنظام 24 ساعة بوضوح.

المتطلبات:
pip install flask pyswisseph geonamescache

طريقة التشغيل:
python personal_chart_reader_v1_2.py

ثم افتح:
http://127.0.0.1:5000
"""

from __future__ import annotations

import math
import json
import os
import sys
import urllib.request
import ssl
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Tuple, Optional

from flask import Flask, request, render_template_string, jsonify

try:
    import swisseph as swe
    SWISSEPH_AVAILABLE = True
except Exception:
    swe = None
    SWISSEPH_AVAILABLE = False


def setup_swiss_ephemeris_path():
    """
    يحاول ضبط مسارات ملفات Swiss Ephemeris تلقائيًا.
    هذا مهم لحساب الكويكبات مثل كايرون، جونو، فيستا، بالاس، سيريس، فولو.
    إذا لم توجد ملفات مثل seas_18.se1 فلن تستطيع pyswisseph حساب هذه الكويكبات.
    """
    if not SWISSEPH_AVAILABLE:
        return

    candidate_paths = []

    # مجلد بجانب ملف التطبيق
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        candidate_paths.append(script_dir)
        candidate_paths.append(os.path.join(script_dir, "sweph"))
        candidate_paths.append(os.path.join(script_dir, "ephe"))
        candidate_paths.append(os.path.join(script_dir, "swisseph"))
    except Exception:
        pass

    # مسارات شائعة على أندرويد / Pydroid
    candidate_paths.extend([
        "/storage/emulated/0/sweph",
        "/storage/emulated/0/Download/sweph",
        "/storage/emulated/0/Pydroid3/sweph",
        "/sdcard/sweph",
        "/sdcard/Download/sweph",
    ])

    # إذا كانت kerykeion مثبتة، غالبًا تحتوي ملفات ephemeris
    try:
        import kerykeion
        kery_path = os.path.dirname(os.path.abspath(kerykeion.__file__))
        candidate_paths.append(os.path.join(kery_path, "sweph"))
    except Exception:
        pass

    # مسارات Linux شائعة
    candidate_paths.extend([
        "/usr/share/swisseph",
        "/usr/local/share/swisseph",
        "/opt/pyvenv/lib/python3.13/site-packages/kerykeion/sweph",
        "/opt/pyvenv/lib64/python3.13/site-packages/kerykeion/sweph",
    ])

    # اختر المسارات الموجودة فقط
    existing = []
    for p in candidate_paths:
        try:
            if p and os.path.isdir(p) and p not in existing:
                existing.append(p)
        except Exception:
            pass

    if existing:
        try:
            swe.set_ephe_path(os.pathsep.join(existing))
        except Exception:
            pass


setup_swiss_ephemeris_path()


ASTEROID_EPHEMERIS_FILENAME = "seas_18.se1"

ASTEROID_EPHEMERIS_URLS = [
    "https://raw.githubusercontent.com/aloistr/swisseph/master/ephe/seas_18.se1",
    "https://raw.githubusercontent.com/chapagain/php-swiss-ephemeris/master/sweph/seas_18.se1",
]


def candidate_sweph_dirs() -> List[str]:
    dirs: List[str] = []

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        dirs.extend([
            script_dir,
            os.path.join(script_dir, "sweph"),
            os.path.join(script_dir, "ephe"),
            os.path.join(script_dir, "swisseph"),
        ])
    except Exception:
        pass

    dirs.extend([
        "/storage/emulated/0/sweph",
        "/storage/emulated/0/Download/sweph",
        "/storage/emulated/0/Pydroid3/sweph",
        "/sdcard/sweph",
        "/sdcard/Download/sweph",
    ])

    try:
        import kerykeion
        kery_path = os.path.dirname(os.path.abspath(kerykeion.__file__))
        dirs.append(os.path.join(kery_path, "sweph"))
    except Exception:
        pass

    clean: List[str] = []
    for d in dirs:
        if d and d not in clean:
            clean.append(d)
    return clean


def find_asteroid_ephemeris_file() -> str:
    for d in candidate_sweph_dirs():
        try:
            f = os.path.join(d, ASTEROID_EPHEMERIS_FILENAME)
            if os.path.isfile(f) and os.path.getsize(f) > 100000:
                return f
        except Exception:
            continue
    return ""


def writable_sweph_dir() -> str:
    for d in candidate_sweph_dirs():
        try:
            os.makedirs(d, exist_ok=True)
            test_file = os.path.join(d, ".write_test")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("ok")
            try:
                os.remove(test_file)
            except Exception:
                pass
            return d
        except Exception:
            continue
    return ""


def download_asteroid_ephemeris_file() -> str:
    existing = find_asteroid_ephemeris_file()
    if existing:
        return existing

    target_dir = writable_sweph_dir()
    if not target_dir:
        return ""

    target_file = os.path.join(target_dir, ASTEROID_EPHEMERIS_FILENAME)

    for url in ASTEROID_EPHEMERIS_URLS:
        try:
            urllib.request.urlretrieve(url, target_file)
            if os.path.isfile(target_file) and os.path.getsize(target_file) > 100000:
                try:
                    swe.set_ephe_path(target_dir)
                except Exception:
                    pass
                setup_swiss_ephemeris_path()
                return target_file
        except Exception:
            try:
                ctx = ssl._create_unverified_context()
                with urllib.request.urlopen(url, timeout=25, context=ctx) as response:
                    data = response.read()
                if len(data) > 100000:
                    with open(target_file, "wb") as f:
                        f.write(data)
                    try:
                        swe.set_ephe_path(target_dir)
                    except Exception:
                        pass
                    setup_swiss_ephemeris_path()
                    return target_file
            except Exception:
                continue

    return ""


def ensure_asteroid_ephemeris_ready() -> bool:
    if not SWISSEPH_AVAILABLE:
        return False

    existing = find_asteroid_ephemeris_file()
    if existing:
        try:
            swe.set_ephe_path(os.path.dirname(existing))
        except Exception:
            setup_swiss_ephemeris_path()
        return True

    downloaded = download_asteroid_ephemeris_file()
    if downloaded:
        try:
            swe.set_ephe_path(os.path.dirname(downloaded))
        except Exception:
            setup_swiss_ephemeris_path()
        return True

    return False


try:
    import geonamescache
    GEONAMESCACHE_AVAILABLE = True
except Exception:
    geonamescache = None
    GEONAMESCACHE_AVAILABLE = False

try:
    from zoneinfo import ZoneInfo
    ZONEINFO_AVAILABLE = True
except Exception:
    ZoneInfo = None
    ZONEINFO_AVAILABLE = False


# ============================================================
# إعدادات عامة
# ============================================================

APP_TITLE = "قراءة الخريطة الشخصية"

SIGNS_AR = [
    "الحمل", "الثور", "الجوزاء", "السرطان",
    "الأسد", "العذراء", "الميزان", "العقرب",
    "القوس", "الجدي", "الدلو", "الحوت"
]

PLANETS = {
    "Sun": {"ar": "الشمس", "id": 0},
    "Moon": {"ar": "القمر", "id": 1},
    "Mercury": {"ar": "عطارد", "id": 2},
    "Venus": {"ar": "الزهرة", "id": 3},
    "Mars": {"ar": "المريخ", "id": 4},
    "Jupiter": {"ar": "المشتري", "id": 5},
    "Saturn": {"ar": "زحل", "id": 6},
    "Uranus": {"ar": "أورانوس", "id": 7},
    "Neptune": {"ar": "نبتون", "id": 8},
    "Pluto": {"ar": "بلوتو", "id": 9},
}

SIGN_RULERS = {
    "الحمل": "المريخ",
    "الثور": "الزهرة",
    "الجوزاء": "عطارد",
    "السرطان": "القمر",
    "الأسد": "الشمس",
    "العذراء": "عطارد",
    "الميزان": "الزهرة",
    "العقرب": "المريخ",
    "القوس": "المشتري",
    "الجدي": "زحل",
    "الدلو": "زحل",
    "الحوت": "المشتري",
}

ELEMENTS = {
    "الحمل": "نار", "الأسد": "نار", "القوس": "نار",
    "الثور": "تراب", "العذراء": "تراب", "الجدي": "تراب",
    "الجوزاء": "هواء", "الميزان": "هواء", "الدلو": "هواء",
    "السرطان": "ماء", "العقرب": "ماء", "الحوت": "ماء",
}

PTOLEMY_TERMS = {
    "الحمل": [(6, "المشتري"), (12, "الزهرة"), (20, "عطارد"), (25, "المريخ"), (30, "زحل")],
    "الثور": [(8, "الزهرة"), (15, "عطارد"), (22, "المشتري"), (27, "زحل"), (30, "المريخ")],
    "الجوزاء": [(6, "عطارد"), (12, "المشتري"), (17, "الزهرة"), (24, "المريخ"), (30, "زحل")],
    "السرطان": [(7, "المريخ"), (13, "الزهرة"), (19, "عطارد"), (26, "المشتري"), (30, "زحل")],
    "الأسد": [(6, "زحل"), (13, "عطارد"), (19, "الزهرة"), (25, "المشتري"), (30, "المريخ")],
    "العذراء": [(7, "عطارد"), (13, "الزهرة"), (17, "المشتري"), (21, "المريخ"), (30, "زحل")],
    "الميزان": [(6, "زحل"), (14, "عطارد"), (21, "المشتري"), (28, "الزهرة"), (30, "المريخ")],
    "العقرب": [(7, "المريخ"), (11, "الزهرة"), (19, "عطارد"), (24, "المشتري"), (30, "زحل")],
    "القوس": [(12, "المشتري"), (17, "الزهرة"), (21, "عطارد"), (26, "زحل"), (30, "المريخ")],
    "الجدي": [(7, "عطارد"), (14, "المشتري"), (22, "الزهرة"), (26, "زحل"), (30, "المريخ")],
    "الدلو": [(7, "عطارد"), (13, "الزهرة"), (20, "المشتري"), (25, "المريخ"), (30, "زحل")],
    "الحوت": [(12, "الزهرة"), (16, "المشتري"), (19, "عطارد"), (28, "المريخ"), (30, "زحل")],
}

# بدائل عربية شائعة لبعض الدول والمدن لتسهيل الاستخدام.
COUNTRY_AR_NAMES = {
    "Iraq": "العراق",
    "Saudi Arabia": "السعودية",
    "Kuwait": "الكويت",
    "Jordan": "الأردن",
    "Egypt": "مصر",
    "United Arab Emirates": "الإمارات",
    "Qatar": "قطر",
    "Bahrain": "البحرين",
    "Oman": "عُمان",
    "Yemen": "اليمن",
    "Syria": "سوريا",
    "Lebanon": "لبنان",
    "Turkey": "تركيا",
    "Iran": "إيران",
    "United States": "الولايات المتحدة",
    "United Kingdom": "بريطانيا",
    "Germany": "ألمانيا",
    "France": "فرنسا",
    "Canada": "كندا",
    "Australia": "أستراليا",
}

# قاموس عربي داخلي للمدن المهمة.
# هذا القاموس لا يحصر التطبيق، بل يساعده على فهم الاسم العربي مباشرة.
# إذا لم يجد المدينة هنا، ينتقل إلى geonamescache للبحث العالمي.
CITY_AR_OVERRIDES = {
    "IQ": {
        "بغداد": {"name": "", "lat": 33.3152, "lon": 44.3661, "timezone": "Asia/Baghdad"},
        "النجف": {"name": "", "lat": 32.0000, "lon": 44.3333, "timezone": "Asia/Baghdad"},
        "نجف": {"name": "", "lat": 32.0000, "lon": 44.3333, "timezone": "Asia/Baghdad"},
        "كربلاء": {"name": "", "lat": 32.6160, "lon": 44.0249, "timezone": "Asia/Baghdad"},
        "الديوانية": {"name": "", "lat": 31.9860, "lon": 44.9250, "timezone": "Asia/Baghdad"},
        "ديوانية": {"name": "", "lat": 31.9860, "lon": 44.9250, "timezone": "Asia/Baghdad"},
        "الشامية": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "شامية": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "Ash Shamiyah": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "Ash shamiyah": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "Ash shamiyh": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "Ash shamiya": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "Al Shamiyah": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "al shamiyah": {"name": "", "lat": 31.9640, "lon": 44.6000, "timezone": "Asia/Baghdad"},
        "الكوفة": {"name": "", "lat": 32.0347, "lon": 44.4033, "timezone": "Asia/Baghdad"},
        "كوفة": {"name": "", "lat": 32.0347, "lon": 44.4033, "timezone": "Asia/Baghdad"},
        "الحلة": {"name": "", "lat": 32.4721, "lon": 44.4217, "timezone": "Asia/Baghdad"},
        "حلة": {"name": "", "lat": 32.4721, "lon": 44.4217, "timezone": "Asia/Baghdad"},
        "البصرة": {"name": "", "lat": 30.5085, "lon": 47.7804, "timezone": "Asia/Baghdad"},
        "بصرة": {"name": "", "lat": 30.5085, "lon": 47.7804, "timezone": "Asia/Baghdad"},
        "الموصل": {"name": "", "lat": 36.3489, "lon": 43.1577, "timezone": "Asia/Baghdad"},
        "موصل": {"name": "", "lat": 36.3489, "lon": 43.1577, "timezone": "Asia/Baghdad"},
        "كركوك": {"name": "", "lat": 35.4681, "lon": 44.3922, "timezone": "Asia/Baghdad"},
        "أربيل": {"name": "", "lat": 36.1911, "lon": 44.0092, "timezone": "Asia/Baghdad"},
        "اربيل": {"name": "", "lat": 36.1911, "lon": 44.0092, "timezone": "Asia/Baghdad"},
        "هولير": {"name": "", "lat": 36.1911, "lon": 44.0092, "timezone": "Asia/Baghdad"},
        "السليمانية": {"name": "", "lat": 35.5570, "lon": 45.4356, "timezone": "Asia/Baghdad"},
        "سليمانية": {"name": "", "lat": 35.5570, "lon": 45.4356, "timezone": "Asia/Baghdad"},
        "الناصرية": {"name": "", "lat": 31.0576, "lon": 46.2573, "timezone": "Asia/Baghdad"},
        "ناصرية": {"name": "", "lat": 31.0576, "lon": 46.2573, "timezone": "Asia/Baghdad"},
        "العمارة": {"name": "", "lat": 31.8356, "lon": 47.1448, "timezone": "Asia/Baghdad"},
        "عمارة": {"name": "", "lat": 31.8356, "lon": 47.1448, "timezone": "Asia/Baghdad"},
        "السماوة": {"name": "", "lat": 31.3180, "lon": 45.2803, "timezone": "Asia/Baghdad"},
        "سماوة": {"name": "", "lat": 31.3180, "lon": 45.2803, "timezone": "Asia/Baghdad"},
        "الكوت": {"name": "", "lat": 32.5147, "lon": 45.8190, "timezone": "Asia/Baghdad"},
        "كوت": {"name": "", "lat": 32.5147, "lon": 45.8190, "timezone": "Asia/Baghdad"},
        "بعقوبة": {"name": "", "lat": 33.7485, "lon": 44.6555, "timezone": "Asia/Baghdad"},
        "ديالى": {"name": "", "lat": 33.7485, "lon": 44.6555, "timezone": "Asia/Baghdad"},
        "تكريت": {"name": "", "lat": 34.6071, "lon": 43.6782, "timezone": "Asia/Baghdad"},
        "دهوك": {"name": "", "lat": 36.8667, "lon": 42.9833, "timezone": "Asia/Baghdad"},
        "الرمادي": {"name": "", "lat": 33.4206, "lon": 43.3078, "timezone": "Asia/Baghdad"},
        "رمادي": {"name": "", "lat": 33.4206, "lon": 43.3078, "timezone": "Asia/Baghdad"},
        "الفلوجة": {"name": "", "lat": 33.3558, "lon": 43.7861, "timezone": "Asia/Baghdad"},
        "فلوجة": {"name": "", "lat": 33.3558, "lon": 43.7861, "timezone": "Asia/Baghdad"},
        "سامراء": {"name": "", "lat": 34.1959, "lon": 43.8857, "timezone": "Asia/Baghdad"},
        "الزبير": {"name": "", "lat": 30.3921, "lon": 47.7018, "timezone": "Asia/Baghdad"},
        "زبير": {"name": "", "lat": 30.3921, "lon": 47.7018, "timezone": "Asia/Baghdad"},
        "القائم": {"name": "", "lat": 34.3686, "lon": 41.0945, "timezone": "Asia/Baghdad"},
        "هيت": {"name": "", "lat": 33.6416, "lon": 42.8251, "timezone": "Asia/Baghdad"},
        "عفك": {"name": "", "lat": 32.0643, "lon": 45.2474, "timezone": "Asia/Baghdad"},
        "الحمزة": {"name": "", "lat": 31.7330, "lon": 44.6600, "timezone": "Asia/Baghdad"},
    },
    "SA": {
        "الرياض": {"name": "", "lat": 24.7136, "lon": 46.6753, "timezone": "Asia/Riyadh"},
        "جدة": {"name": "", "lat": 21.4858, "lon": 39.1925, "timezone": "Asia/Riyadh"},
        "مكة": {"name": "", "lat": 21.3891, "lon": 39.8579, "timezone": "Asia/Riyadh"},
        "مكة المكرمة": {"name": "", "lat": 21.3891, "lon": 39.8579, "timezone": "Asia/Riyadh"},
        "المدينة": {"name": "", "lat": 24.5247, "lon": 39.5692, "timezone": "Asia/Riyadh"},
        "المدينة المنورة": {"name": "", "lat": 24.5247, "lon": 39.5692, "timezone": "Asia/Riyadh"},
        "الدمام": {"name": "", "lat": 26.4207, "lon": 50.0888, "timezone": "Asia/Riyadh"},
        "الخبر": {"name": "", "lat": 26.2172, "lon": 50.1971, "timezone": "Asia/Riyadh"},
        "الطائف": {"name": "", "lat": 21.4373, "lon": 40.5127, "timezone": "Asia/Riyadh"},
        "تبوك": {"name": "", "lat": 28.3838, "lon": 36.5662, "timezone": "Asia/Riyadh"},
        "أبها": {"name": "", "lat": 18.2164, "lon": 42.5053, "timezone": "Asia/Riyadh"},
        "ابها": {"name": "", "lat": 18.2164, "lon": 42.5053, "timezone": "Asia/Riyadh"},
        "بريدة": {"name": "", "lat": 26.3592, "lon": 43.9818, "timezone": "Asia/Riyadh"},
        "حائل": {"name": "", "lat": 27.5114, "lon": 41.7208, "timezone": "Asia/Riyadh"},
        "جازان": {"name": "", "lat": 16.8892, "lon": 42.5511, "timezone": "Asia/Riyadh"},
    },
    "KW": {
        "الكويت": {"name": "", "lat": 29.3759, "lon": 47.9774, "timezone": "Asia/Kuwait"},
        "مدينة الكويت": {"name": "", "lat": 29.3759, "lon": 47.9774, "timezone": "Asia/Kuwait"},
    },
    "JO": {
        "عمان": {"name": "", "lat": 31.9539, "lon": 35.9106, "timezone": "Asia/Amman"},
        "عمّان": {"name": "", "lat": 31.9539, "lon": 35.9106, "timezone": "Asia/Amman"},
        "إربد": {"name": "", "lat": 32.5556, "lon": 35.8500, "timezone": "Asia/Amman"},
        "اربد": {"name": "", "lat": 32.5556, "lon": 35.8500, "timezone": "Asia/Amman"},
        "الزرقاء": {"name": "", "lat": 32.0728, "lon": 36.0870, "timezone": "Asia/Amman"},
        "العقبة": {"name": "", "lat": 29.5267, "lon": 35.0078, "timezone": "Asia/Amman"},
    },
    "EG": {
        "القاهرة": {"name": "", "lat": 30.0444, "lon": 31.2357, "timezone": "Africa/Cairo"},
        "الجيزة": {"name": "", "lat": 30.0131, "lon": 31.2089, "timezone": "Africa/Cairo"},
        "الإسكندرية": {"name": "", "lat": 31.2001, "lon": 29.9187, "timezone": "Africa/Cairo"},
        "الاسكندرية": {"name": "", "lat": 31.2001, "lon": 29.9187, "timezone": "Africa/Cairo"},
        "الأقصر": {"name": "", "lat": 25.6872, "lon": 32.6396, "timezone": "Africa/Cairo"},
        "الاقصر": {"name": "", "lat": 25.6872, "lon": 32.6396, "timezone": "Africa/Cairo"},
        "أسوان": {"name": "", "lat": 24.0889, "lon": 32.8998, "timezone": "Africa/Cairo"},
        "اسوان": {"name": "", "lat": 24.0889, "lon": 32.8998, "timezone": "Africa/Cairo"},
        "المنصورة": {"name": "", "lat": 31.0409, "lon": 31.3785, "timezone": "Africa/Cairo"},
        "طنطا": {"name": "", "lat": 30.7865, "lon": 31.0004, "timezone": "Africa/Cairo"},
        "بورسعيد": {"name": "", "lat": 31.2653, "lon": 32.3019, "timezone": "Africa/Cairo"},
        "السويس": {"name": "", "lat": 29.9668, "lon": 32.5498, "timezone": "Africa/Cairo"},
    },
    "AE": {
        "دبي": {"name": "", "lat": 25.2048, "lon": 55.2708, "timezone": "Asia/Dubai"},
        "أبوظبي": {"name": "", "lat": 24.4539, "lon": 54.3773, "timezone": "Asia/Dubai"},
        "ابوظبي": {"name": "", "lat": 24.4539, "lon": 54.3773, "timezone": "Asia/Dubai"},
        "الشارقة": {"name": "", "lat": 25.3463, "lon": 55.4209, "timezone": "Asia/Dubai"},
        "العين": {"name": "", "lat": 24.2075, "lon": 55.7447, "timezone": "Asia/Dubai"},
        "عجمان": {"name": "", "lat": 25.4052, "lon": 55.5136, "timezone": "Asia/Dubai"},
        "رأس الخيمة": {"name": "", "lat": 25.7895, "lon": 55.9432, "timezone": "Asia/Dubai"},
        "راس الخيمة": {"name": "", "lat": 25.7895, "lon": 55.9432, "timezone": "Asia/Dubai"},
    },
    "QA": {
        "الدوحة": {"name": "", "lat": 25.2854, "lon": 51.5310, "timezone": "Asia/Qatar"},
        "دوحة": {"name": "", "lat": 25.2854, "lon": 51.5310, "timezone": "Asia/Qatar"},
    },
    "BH": {
        "المنامة": {"name": "", "lat": 26.2235, "lon": 50.5876, "timezone": "Asia/Bahrain"},
        "منامة": {"name": "", "lat": 26.2235, "lon": 50.5876, "timezone": "Asia/Bahrain"},
    },
    "OM": {
        "مسقط": {"name": "", "lat": 23.5880, "lon": 58.3829, "timezone": "Asia/Muscat"},
        "صلالة": {"name": "", "lat": 17.0194, "lon": 54.1108, "timezone": "Asia/Muscat"},
    },
    "YE": {
        "صنعاء": {"name": "", "lat": 15.3694, "lon": 44.1910, "timezone": "Asia/Aden"},
        "عدن": {"name": "", "lat": 12.7855, "lon": 45.0187, "timezone": "Asia/Aden"},
        "تعز": {"name": "", "lat": 13.5795, "lon": 44.0209, "timezone": "Asia/Aden"},
    },
    "SY": {
        "دمشق": {"name": "", "lat": 33.5138, "lon": 36.2765, "timezone": "Asia/Damascus"},
        "حلب": {"name": "", "lat": 36.2021, "lon": 37.1343, "timezone": "Asia/Damascus"},
        "حمص": {"name": "", "lat": 34.7324, "lon": 36.7137, "timezone": "Asia/Damascus"},
        "حماة": {"name": "", "lat": 35.1318, "lon": 36.7578, "timezone": "Asia/Damascus"},
        "اللاذقية": {"name": "", "lat": 35.5317, "lon": 35.7901, "timezone": "Asia/Damascus"},
        "اللاذقيه": {"name": "", "lat": 35.5317, "lon": 35.7901, "timezone": "Asia/Damascus"},
    },
    "LB": {
        "بيروت": {"name": "", "lat": 33.8938, "lon": 35.5018, "timezone": "Asia/Beirut"},
        "طرابلس": {"name": "", "lat": 34.4367, "lon": 35.8497, "timezone": "Asia/Beirut"},
        "صيدا": {"name": "", "lat": 33.5571, "lon": 35.3715, "timezone": "Asia/Beirut"},
        "صور": {"name": "", "lat": 33.2704, "lon": 35.2038, "timezone": "Asia/Beirut"},
    },
    "TR": {
        "اسطنبول": {"name": "", "lat": 41.0082, "lon": 28.9784, "timezone": "Europe/Istanbul"},
        "إسطنبول": {"name": "", "lat": 41.0082, "lon": 28.9784, "timezone": "Europe/Istanbul"},
        "انقرة": {"name": "", "lat": 39.9334, "lon": 32.8597, "timezone": "Europe/Istanbul"},
        "أنقرة": {"name": "", "lat": 39.9334, "lon": 32.8597, "timezone": "Europe/Istanbul"},
        "ازمير": {"name": "", "lat": 38.4237, "lon": 27.1428, "timezone": "Europe/Istanbul"},
        "إزمير": {"name": "", "lat": 38.4237, "lon": 27.1428, "timezone": "Europe/Istanbul"},
        "اورفا": {"name": "", "lat": 37.1674, "lon": 38.7955, "timezone": "Europe/Istanbul"},
        "أورفا": {"name": "", "lat": 37.1674, "lon": 38.7955, "timezone": "Europe/Istanbul"},
    },
    "IR": {
        "طهران": {"name": "", "lat": 35.6892, "lon": 51.3890, "timezone": "Asia/Tehran"},
        "مشهد": {"name": "", "lat": 36.2605, "lon": 59.6168, "timezone": "Asia/Tehran"},
        "قم": {"name": "", "lat": 34.6416, "lon": 50.8746, "timezone": "Asia/Tehran"},
        "اصفهان": {"name": "", "lat": 32.6546, "lon": 51.6680, "timezone": "Asia/Tehran"},
        "أصفهان": {"name": "", "lat": 32.6546, "lon": 51.6680, "timezone": "Asia/Tehran"},
        "شيراز": {"name": "", "lat": 29.5918, "lon": 52.5837, "timezone": "Asia/Tehran"},
    },
}

# أسماء بديلة تستخدم في البحث داخل geonamescache إذا لم تكن المدينة في القاموس أعلاه.
CITY_ALIASES = {
    "بغداد": ["Baghdad"],
    "النجف": ["Najaf", "An Najaf"],
    "كربلاء": ["Karbala", "Karbala'"],
    "الديوانية": ["Ad Diwaniyah", "Diwaniyah"],
    "الشامية": ["Ash Shamiyah", "Ash Shāmīyah"],
    "البصرة": ["Basra", "Al Basrah"],
    "الموصل": ["Mosul", "Al Mawsil"],
    "كركوك": ["Kirkuk"],
    "أربيل": ["Erbil", "Arbil"],
    "اربيل": ["Erbil", "Arbil"],
    "السليمانية": ["Sulaymaniyah", "As Sulaymaniyah"],
    "الناصرية": ["Nasiriyah", "An Nasiriyah"],
    "الحلة": ["Al Hillah", "Hillah"],
    "الرمادي": ["Ramadi", "Ar Ramadi"],
    "العمارة": ["Amarah", "Al Amarah"],
    "السماوة": ["Samawah", "As Samawah"],
    "الكوت": ["Kut", "Al Kut"],
    "بعقوبة": ["Baqubah"],
    "تكريت": ["Tikrit"],
    "دهوك": ["Duhok", "Dihok"],
    "الرياض": ["Riyadh"],
    "جدة": ["Jeddah"],
    "مكة": ["Mecca", "Makkah"],
    "المدينة": ["Medina"],
    "القاهرة": ["Cairo"],
    "الإسكندرية": ["Alexandria"],
    "دبي": ["Dubai"],
    "أبوظبي": ["Abu Dhabi"],
    "عمّان": ["Amman"],
    "عمان": ["Amman", "Muscat"],
}


@dataclass
class BodyPosition:
    name_en: str
    name_ar: str
    lon: float
    sign: str
    degree: float
    house: Optional[int] = None
    term: Optional[str] = None
    retrograde: bool = False


# ============================================================
# قاعدة المدن العالمية
# ============================================================

def build_country_list() -> List[Dict[str, str]]:
    """
    ترجع قائمة الدول أبجديًا كما هي، مع ضمان وجود العراق داخل موضعه الطبيعي.
    لا يتم تثبيت العراق في الأعلى؛ فقط نضمن عدم اختفائه من القائمة.
    """
    items: List[Dict[str, str]] = []

    if GEONAMESCACHE_AVAILABLE:
        gc = geonamescache.GeonamesCache()
        countries = gc.get_countries()

        for code, info in countries.items():
            en_name = info.get("name", code)

            # نترك القائمة أبجدية إنكليزية واضحة للمستخدم،
            # ونظهر العراق باسم مزدوج حتى يكون سهل العثور عليه.
            if code == "IQ":
                display = "Iraq / العراق"
            else:
                display = COUNTRY_AR_NAMES.get(en_name, en_name)

            items.append({"code": code, "name": display})

    # ضمان العراق حتى إذا لم يرجعه مصدر الدول لأي سبب
    if not any(item.get("code") == "IQ" for item in items):
        items.append({"code": "IQ", "name": "Iraq / العراق"})

    # ترتيب أبجدي طبيعي حسب الاسم الظاهر
    items.sort(key=lambda x: x["name"])
    return items


def get_city_candidates(country_code: str) -> List[Dict[str, object]]:
    """
    يرجع مدن الدولة من geonamescache.
    نأخذ المدن الأكثر شهرة أولًا حسب عدد السكان.
    """
    if not GEONAMESCACHE_AVAILABLE:
        return [
            {"name": "", "display": "Baghdad", "lat": 33.3152, "lon": 44.3661, "timezone": "Asia/Baghdad", "population": 0}
        ]

    gc = geonamescache.GeonamesCache()
    cities = gc.get_cities()

    result = []
    for _, c in cities.items():
        if c.get("countrycode") != country_code:
            continue

        name = c.get("name", "")
        lat = float(c.get("latitude", 0.0))
        lon = float(c.get("longitude", 0.0))
        timezone = c.get("timezone", "")
        population = int(c.get("population", 0) or 0)

        result.append({
            "name": name,
            "display": name,
            "lat": lat,
            "lon": lon,
            "timezone": timezone,
            "population": population,
        })

    result.sort(key=lambda x: int(x.get("population", 0)), reverse=True)
    return result


def normalize_text(s: str) -> str:
    s = (s or "").strip().lower()
    replacements = {
        "أ": "ا", "إ": "ا", "آ": "ا",
        "ى": "ي", "ة": "ه",
        "’": "'", "‘": "'", "`": "'",
    }
    for a, b in replacements.items():
        s = s.replace(a, b)
    return s


def find_city(country_code: str, city_input: str) -> Optional[Dict[str, object]]:
    """
    يبحث عن المدينة داخل الدولة.
    يقبل الاسم الإنجليزي الموجود في geonamescache،
    ويقبل بعض الأسماء العربية الشائعة عبر CITY_ALIASES.
    """
    city_input = (city_input or "").strip()
    if not city_input:
        return None

    # 1) البحث أولًا في القاموس العربي الداخلي.
    normalized_input = normalize_text(city_input)
    overrides = CITY_AR_OVERRIDES.get(country_code, {})
    for ar_name, info in overrides.items():
        if normalize_text(ar_name) == normalized_input:
            return {
                "name": info["name"],
                "display": ar_name,
                "lat": float(info["lat"]),
                "lon": float(info["lon"]),
                "timezone": info["timezone"],
                "population": 0,
            }

    candidates = get_city_candidates(country_code)
    wanted_norm = normalize_text(city_input)

    # تحويل الاسم العربي إلى احتمالات إنجليزية إن وجد.
    search_names = [city_input]
    if city_input in CITY_ALIASES:
        search_names.extend(CITY_ALIASES[city_input])

    normalized_search = [normalize_text(x) for x in search_names]

    # تطابق كامل
    for c in candidates:
        c_norm = normalize_text(str(c["name"]))
        if c_norm in normalized_search:
            return c

    # يبدأ بنفس الاسم
    for c in candidates:
        c_norm = normalize_text(str(c["name"]))
        if any(c_norm.startswith(s) or s.startswith(c_norm) for s in normalized_search if s):
            return c

    # يحتوي الاسم
    for c in candidates:
        c_norm = normalize_text(str(c["name"]))
        if any(s in c_norm or c_norm in s for s in normalized_search if len(s) >= 3):
            return c

    return None


def timezone_offset_for_birth(tz_name: str, year: int, month: int, day: int, hour: int, minute: int) -> float:
    """
    يحسب فرق التوقيت من اسم المنطقة الزمنية إذا أمكن.
    إن لم يتوفر zoneinfo أو اسم المنطقة، يرجع 3 كافتراضي للعراق.
    """
    if not tz_name or not ZONEINFO_AVAILABLE:
        return 3.0

    try:
        dt = datetime(year, month, day, hour, minute, tzinfo=ZoneInfo(tz_name))
        offset = dt.utcoffset()
        if offset is None:
            return 3.0
        return offset.total_seconds() / 3600.0
    except Exception:
        return 3.0


def city_suggestions_for_country(country_code: str, limit: int = 120) -> List[str]:
    suggestions: List[str] = []

    # نضع أسماء المدن العربية في البداية إن كانت موجودة في القاموس.
    for ar_name in CITY_AR_OVERRIDES.get(country_code, {}).keys():
        if ar_name not in suggestions:
            suggestions.append(ar_name)

    # ترتيب خاص للعراق حتى تظهر المدن المطلوبة بوضوح في أول القائمة.
    if country_code == "IQ":
        priority = [
            "بغداد", "النجف", "كربلاء", "الديوانية", "الشامية", "البصرة",
            "الموصل", "كركوك", "أربيل", "السليمانية", "الناصرية", "الحلة",
            "الرمادي", "العمارة", "السماوة", "الكوت", "بعقوبة", "تكريت",
            "دهوك", "الفلوجة", "سامراء"
        ]
        ordered = []
        for x in priority + suggestions:
            if x not in ordered:
                ordered.append(x)
        suggestions = ordered

    # ثم نضيف أشهر المدن العالمية من geonamescache.
    cities = get_city_candidates(country_code)
    for c in cities[:limit]:
        name = str(c["name"])
        if name not in suggestions:
            suggestions.append(name)

    return suggestions[:limit + 120]


# ============================================================
# أدوات حسابية
# ============================================================

def normalize_deg(x: float) -> float:
    return x % 360.0


def sign_from_lon(lon: float) -> Tuple[str, float]:
    lon = normalize_deg(lon)
    idx = int(lon // 30)
    sign = SIGNS_AR[idx]
    degree = lon - idx * 30
    return sign, degree


def format_degree(deg: float) -> str:
    d = int(deg)
    m = int(round((deg - d) * 60))
    if m == 60:
        d += 1
        m = 0
    return f"{d:02d}°{m:02d}′"


def angular_distance(a: float, b: float) -> float:
    diff = abs(normalize_deg(a - b))
    return min(diff, 360 - diff)


def get_ptolemy_term(sign: str, degree: float) -> str:
    terms = PTOLEMY_TERMS.get(sign, [])
    for end_degree, ruler in terms:
        if degree <= end_degree:
            return ruler
    return terms[-1][1] if terms else ""


def house_from_cusps(lon: float, cusps: List[float]) -> int:
    lon = normalize_deg(lon)
    for i in range(12):
        start = normalize_deg(cusps[i])
        end = normalize_deg(cusps[(i + 1) % 12])
        if start <= end:
            if start <= lon < end:
                return i + 1
        else:
            if lon >= start or lon < end:
                return i + 1
    return 1


def calculate_chart(
    year: int, month: int, day: int,
    hour: int, minute: int,
    timezone: float,
    lat: float, lon_geo: float,
    house_system: str = "P"
) -> Tuple[Dict[str, BodyPosition], List[float], Dict[str, float]]:
    if not SWISSEPH_AVAILABLE:
        raise RuntimeError("مكتبة pyswisseph غير مثبتة. نفّذ: pip install pyswisseph")

    local_decimal = hour + minute / 60.0
    ut_decimal = local_decimal - timezone

    base = datetime(year, month, day)
    day_shift = 0
    while ut_decimal < 0:
        ut_decimal += 24
        day_shift -= 1
    while ut_decimal >= 24:
        ut_decimal -= 24
        day_shift += 1

    from datetime import timedelta
    ut_date = base + timedelta(days=day_shift)

    jd_ut = swe.julday(ut_date.year, ut_date.month, ut_date.day, ut_decimal)
    flags = swe.FLG_SWIEPH | swe.FLG_SPEED

    cusps_tuple, ascmc = swe.houses(jd_ut, lat, lon_geo, house_system.encode("ascii"))
    cusps = list(cusps_tuple[:12])

    positions: Dict[str, BodyPosition] = {}
    for key, meta in PLANETS.items():
        result, retflag = swe.calc_ut(jd_ut, meta["id"], flags)
        p_lon = normalize_deg(result[0])
        speed = result[3]
        sign, degree = sign_from_lon(p_lon)
        house = house_from_cusps(p_lon, cusps)
        term = get_ptolemy_term(sign, degree)
        positions[key] = BodyPosition(
            name_en=key,
            name_ar=meta["ar"],
            lon=p_lon,
            sign=sign,
            degree=degree,
            house=house,
            term=term,
            retrograde=speed < 0
        )

    asc = normalize_deg(ascmc[0])
    mc = normalize_deg(ascmc[1])
    asc_sign, asc_degree = sign_from_lon(asc)
    mc_sign, mc_degree = sign_from_lon(mc)

    angles = {
        "ASC": asc,
        "MC": mc,
        "ASC_sign": asc_sign,
        "ASC_degree": asc_degree,
        "MC_sign": mc_sign,
        "MC_degree": mc_degree,
        "JD_UT": jd_ut
    }

    return positions, cusps, angles


# ============================================================
# محرك التفسير V1
# ============================================================

def add_unique(items: List[str], text: str):
    if text not in items:
        items.append(text)


def analyze_elements(positions: Dict[str, BodyPosition]) -> Dict[str, int]:
    weights = {
        "Sun": 3, "Moon": 3, "Mercury": 2, "Venus": 2,
        "Mars": 2, "Jupiter": 1, "Saturn": 1
    }
    scores = {"نار": 0, "تراب": 0, "هواء": 0, "ماء": 0}
    for key, weight in weights.items():
        sign = positions[key].sign
        scores[ELEMENTS[sign]] += weight
    return scores


def strongest_element(scores: Dict[str, int]) -> str:
    return max(scores, key=lambda k: scores[k])


def detect_major_aspects(positions: Dict[str, BodyPosition]) -> List[Tuple[str, str, str, float]]:
    aspect_defs = [
        ("اقتران", 0, 8),
        ("تسديس", 60, 4),
        ("تربيع", 90, 6),
        ("تثليث", 120, 6),
        ("مقابلة", 180, 6),
    ]
    keys = list(positions.keys())
    aspects = []
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a = positions[keys[i]]
            b = positions[keys[j]]
            dist = angular_distance(a.lon, b.lon)
            for asp_name, asp_deg, orb in aspect_defs:
                if abs(dist - asp_deg) <= orb:
                    aspects.append((a.name_ar, b.name_ar, asp_name, round(abs(dist - asp_deg), 2)))
                    break
    return aspects


def generate_strengths(positions, angles, element_scores, aspects) -> List[str]:
    strengths: List[str] = []

    sun = positions["Sun"]
    moon = positions["Moon"]
    mercury = positions["Mercury"]
    venus = positions["Venus"]
    mars = positions["Mars"]
    jupiter = positions["Jupiter"]
    saturn = positions["Saturn"]
    asc_sign = str(angles["ASC_sign"])
    asc_ruler = SIGN_RULERS[asc_sign]

    dominant = strongest_element(element_scores)
    if dominant == "نار":
        add_unique(strengths, "يمتلك دافعًا داخليًا واضحًا، وحضورًا قويًا عند البدء أو المبادرة، وهذا يساعده على التحرك حين يتردد الآخرون.")
    elif dominant == "تراب":
        add_unique(strengths, "يمتلك حسًا عمليًا وقدرة على بناء النتائج خطوة بعد خطوة، وهذا يمنحه قابلية جيدة للثبات وتحويل الأفكار إلى واقع.")
    elif dominant == "هواء":
        add_unique(strengths, "يمتلك عقلًا نشطًا وقدرة على الفهم والربط والكلام، وهذا يجعله مناسبًا للتعلم والتواصل وتبادل الأفكار.")
    elif dominant == "ماء":
        add_unique(strengths, "يمتلك حسًا عاطفيًا وحدسًا عاليًا، ويستطيع التقاط ما لا يُقال بسهولة، وهذا يساعده في فهم الناس والظروف العميقة.")

    if sun.house in [1, 5, 9, 10, 11]:
        add_unique(strengths, "لديه طاقة ظهور وتأثير، وقد يستطيع أن يترك بصمة واضحة عندما يجد المجال المناسب للتعبير عن ذاته.")
    if moon.house in [4, 5, 7, 9, 11]:
        add_unique(strengths, "يمتلك قابلية للتعاطف وبناء روابط إنسانية، وقد يكون وجوده مطمئنًا لمن حوله إذا شعر بالأمان الداخلي.")
    if mercury.house in [1, 3, 6, 9, 10]:
        add_unique(strengths, "قوة التفكير والملاحظة من أبرز مفاتيحه، ولديه قابلية جيدة للتعلم، التحليل، الكتابة، أو شرح الأفكار.")
    if venus.house in [1, 2, 5, 7, 10, 11]:
        add_unique(strengths, "فيه ذوق وحس جمالي أو اجتماعي، ويستطيع جذب القبول عندما يستخدم اللطف والمرونة بدل الضغط.")
    if mars.house in [1, 3, 6, 10]:
        add_unique(strengths, "يمتلك طاقة عمل ومواجهة، وإذا وجّهها جيدًا يصبح قادرًا على الإنجاز والدفاع عن أهدافه.")
    if jupiter.house in [1, 2, 5, 9, 10, 11]:
        add_unique(strengths, "لديه قابلية للنمو والتوسع واكتساب الخبرة، وقد يستفيد كثيرًا من التعليم والسفر والانفتاح على تجارب جديدة.")
    if saturn.house in [1, 6, 10, 11]:
        add_unique(strengths, "رغم وجود المسؤوليات، لديه قدرة على النضج والتحمل وبناء مكانة تدريجية إذا التزم بخطة طويلة النفس.")

    add_unique(strengths, f"حاكم الطالع هو {asc_ruler}، وهذا يجعله مفتاحًا مهمًا في فهم الشخصية واتجاه الحياة؛ كلما نضجت دلالته في الخريطة ظهر الشخص بصورة أقوى وأكثر توازنًا.")

    for a, b, asp, orb in aspects:
        if asp in ["تثليث", "تسديس"] and ("الشمس" in [a, b] or "القمر" in [a, b] or "عطارد" in [a, b] or "الزهرة" in [a, b]):
            add_unique(strengths, f"يوجد انسجام بين {a} و{b}، وهذا يعطي قابلية طبيعية لاستخدام هذه الطاقة بصورة إيجابية عند التدريب والوعي.")
            break

    return strengths[:6]


def generate_growth_notes(positions, element_scores, aspects) -> List[str]:
    notes: List[str] = []

    weakest = min(element_scores, key=lambda k: element_scores[k])
    if weakest == "نار":
        add_unique(notes, "يحتاج إلى تقوية روح المبادرة وعدم انتظار التشجيع دائمًا قبل البدء.")
    elif weakest == "تراب":
        add_unique(notes, "يحتاج إلى تحويل الأفكار والمشاعر إلى خطوات عملية، لأن كثرة التخطيط بلا تنفيذ قد تضعف النتائج.")
    elif weakest == "هواء":
        add_unique(notes, "يحتاج إلى التعبير والحوار وعدم كتمان الأفكار، لأن الصمت الطويل قد يخلق سوء فهم.")
    elif weakest == "ماء":
        add_unique(notes, "يحتاج إلى الإصغاء لمشاعره وعدم تجاهل الجانب العاطفي، لأن التماسك الظاهري لا يعني غياب التأثر الداخلي.")

    moon = positions["Moon"]
    mercury = positions["Mercury"]
    venus = positions["Venus"]
    mars = positions["Mars"]
    saturn = positions["Saturn"]

    if moon.sign in ["الجدي", "العقرب", "العذراء"]:
        add_unique(notes, "قد يميل إلى ضبط مشاعره أو إخفائها، لذلك يحتاج إلى مساحة آمنة للتعبير بدل الكتمان الطويل.")
    if mercury.retrograde:
        add_unique(notes, "طريقة تفكيره قد تكون داخلية وعميقة، لكنه يحتاج إلى التأكد من وضوح كلامه حتى لا يُفهم بعكس ما يقصد.")
    if venus.sign in ["الحمل", "العذراء", "العقرب", "الجدي"]:
        add_unique(notes, "في العلاقات أو القبول العاطفي يحتاج إلى التوازن بين الرغبة والسيطرة أو بين الحب والخوف من الخيبة.")
    if mars.sign in ["الحمل", "العقرب", "الجدي"]:
        add_unique(notes, "طاقته قوية، لكنها تحتاج إلى تهذيب حتى لا تتحول إلى اندفاع أو توتر في المواقف الحساسة.")
    if saturn.house in [1, 4, 7, 10, 12]:
        add_unique(notes, "قد يشعر بثقل مسؤولية أو جدية مبكرة في أحد محاور حياته، لذلك يحتاج إلى عدم القسوة على نفسه.")

    for a, b, asp, orb in aspects:
        if asp in ["تربيع", "مقابلة"]:
            if "القمر" in [a, b]:
                add_unique(notes, f"يوجد ضغط على الجانب النفسي والعاطفي بين {a} و{b}، وهذا يحتاج إلى وعي بالمشاعر قبل اتخاذ القرارات.")
            elif "المريخ" in [a, b]:
                add_unique(notes, f"يوجد توتر حركي أو انفعالي بين {a} و{b}، ومن الأفضل تصريف الطاقة في عمل أو رياضة أو إنجاز واضح.")
            elif "زحل" in [a, b]:
                add_unique(notes, f"يوجد اختبار في الصبر والمسؤولية بين {a} و{b}، وهذا لا يعني الفشل بل يعني أن النجاح يحتاج إلى وقت وتنظيم.")
    return notes[:6]


def generate_creativity(positions, angles, element_scores) -> List[str]:
    creativity: List[str] = []

    mercury = positions["Mercury"]
    venus = positions["Venus"]
    mars = positions["Mars"]
    sun = positions["Sun"]
    moon = positions["Moon"]
    jupiter = positions["Jupiter"]

    if mercury.house in [1, 3, 6, 9, 10] or mercury.sign in ["الجوزاء", "العذراء", "الدلو"]:
        add_unique(creativity, "الإبداع الذهني واللغوي: الكتابة، التعليم، الشرح، التحليل، البرمجة، أو ترتيب المعلومات.")
    if venus.house in [1, 2, 5, 7, 10] or venus.sign in ["الثور", "الميزان", "الحوت"]:
        add_unique(creativity, "الإبداع الجمالي والاجتماعي: التصميم، الذوق، الفن، التجميل، العلاقات العامة، أو صناعة أجواء مريحة حوله.")
    if mars.house in [1, 3, 5, 6, 10] or mars.sign in ["الحمل", "الأسد", "العقرب", "الجدي"]:
        add_unique(creativity, "الإبداع العملي والحركي: الإنجاز، المبادرة، العمل الميداني، الرياضة، القيادة، أو المشاريع التي تحتاج شجاعة.")
    if moon.house in [4, 5, 8, 12] or moon.sign in ["السرطان", "العقرب", "الحوت"]:
        add_unique(creativity, "الإبداع العاطفي والحدسي: فهم النفوس، الرعاية، العلاج، القصص، التأمل، أو قراءة ما وراء الظاهر.")
    if jupiter.house in [3, 9, 10, 11] or jupiter.sign in ["القوس", "الحوت", "السرطان"]:
        add_unique(creativity, "الإبداع المعرفي والتوجيهي: التعليم العالي، الإرشاد، السفر، الفلسفة، أو تحويل التجارب إلى حكمة.")
    if sun.house in [5, 10, 11] or sun.sign in ["الحمل", "الأسد", "القوس"]:
        add_unique(creativity, "الإبداع القيادي: الظهور، التأثير في الجمهور، إدارة مبادرة، أو تقديم نفسه بثقة أمام الآخرين.")

    dominant = strongest_element(element_scores)
    if dominant == "نار":
        add_unique(creativity, "أفضل بيئة لإبداعه هي البيئة التي تسمح بالمبادرة والقرار السريع وعدم تقييد الحماس.")
    elif dominant == "تراب":
        add_unique(creativity, "أفضل بيئة لإبداعه هي البيئة المنظمة التي تسمح ببناء نتائج ملموسة وقياس التقدم.")
    elif dominant == "هواء":
        add_unique(creativity, "أفضل بيئة لإبداعه هي البيئة التي تسمح بالحوار، الأفكار، التعلم، والتواصل مع الناس.")
    elif dominant == "ماء":
        add_unique(creativity, "أفضل بيئة لإبداعه هي البيئة الهادئة التي تسمح بالتركيز العاطفي والحدسي والتعبير العميق.")

    return creativity[:6] if creativity else ["الإبداع يظهر عندما يُمنح الشخص وقتًا كافيًا لاكتشاف ما يحب، بدل دفعه إلى مجال لا يشبه طبيعته."]


def generate_challenges(positions, aspects) -> List[str]:
    challenges: List[str] = []

    moon = positions["Moon"]
    mercury = positions["Mercury"]
    venus = positions["Venus"]
    mars = positions["Mars"]
    saturn = positions["Saturn"]
    neptune = positions["Neptune"]
    pluto = positions["Pluto"]

    if moon.house in [8, 12] or moon.sign in ["العقرب", "الجدي", "الحوت"]:
        add_unique(challenges, "نخشى عليه من كتمان المشاعر أو حمل أعباء نفسية بصمت، لذلك يحتاج إلى شخص أو مساحة يستطيع أن يتكلم فيها بصدق.")
    if mercury.house in [6, 8, 12] or mercury.sign in ["العذراء", "الجوزاء", "العقرب"]:
        add_unique(challenges, "نخشى عليه من التفكير الزائد أو تحليل التفاصيل بطريقة متعبة، خصوصًا وقت القلق أو انتظار النتائج.")
    if venus.house in [8, 12] or venus.sign in ["العقرب", "العذراء", "الجدي", "الحمل"]:
        add_unique(challenges, "في العلاقات، يحتاج إلى الحذر من التعلق المرهق أو اختبار الحب بطريقة قاسية على نفسه وعلى الآخر.")
    if mars.house in [1, 7, 8, 12] or mars.sign in ["الحمل", "العقرب", "الجدي"]:
        add_unique(challenges, "نخشى عليه من الانفعال السريع أو الدخول في مواجهة قبل اكتمال الصورة، لذلك يحتاج إلى مهلة قصيرة قبل القرار.")
    if saturn.house in [1, 4, 7, 10, 12]:
        add_unique(challenges, "قد تظهر في حياته مسؤوليات أو شعور بالضغط، والتحدي هنا أن لا يتحول الالتزام إلى قسوة على الذات.")
    if neptune.house in [1, 7, 10, 12]:
        add_unique(challenges, "يحتاج إلى وضوح في الوعود والعلاقات والاختيارات، لأن الغموض الطويل قد يجعله يعلّق آماله على صورة غير مكتملة.")
    if pluto.house in [1, 4, 7, 8, 10]:
        add_unique(challenges, "قد يمر بتجارب عميقة تغيّر نظرته لنفسه أو للناس، والتحدي أن لا يسمح للخوف أو السيطرة بأن يقود قراراته.")

    for a, b, asp, orb in aspects:
        if asp in ["تربيع", "مقابلة"]:
            if set([a, b]) & set(["القمر", "الزهرة"]):
                add_unique(challenges, f"هناك حساسية عاطفية واضحة مرتبطة باتصال {a} مع {b}، لذلك من المهم عدم اتخاذ قرار عاطفي في لحظة ضغط.")
            if set([a, b]) & set(["عطارد", "المريخ"]):
                add_unique(challenges, f"اتصال {a} مع {b} قد يزيد حدّة الكلام أو سرعة الرد، لذلك يحتاج إلى تهدئة الفكرة قبل التعبير عنها.")
            if set([a, b]) & set(["زحل"]):
                add_unique(challenges, f"اتصال {a} مع {b} قد يدل على اختبار وتأخير، لكنه يصبح مصدر قوة إذا قُوبل بالصبر والتنظيم.")

    return challenges[:7] if challenges else ["التحدي الأهم ليس وجود خطر واضح، بل ضرورة اختيار البيئة المناسبة وعدم ترك الطاقات القوية بلا توجيه."]




def gender_words(gender: str) -> Dict[str, str]:
    """
    كلمات توجيه الخطاب حسب الجنس المختار.
    نستخدمها في جمل موجهة، لا في استبدال عشوائي داخل الكلمات.
    """
    if gender == "أنثى":
        return {
            "you": "أنتِ",
            "can": "تستطيعين",
            "need": "تحتاجين",
            "have": "لديكِ",
            "appear": "تظهرين",
            "carry": "تحملين",
            "benefit": "تستفيدين",
            "watch": "تنتبهين",
            "your_chart": "خريطتكِ",
            "your_self": "نفسكِ",
            "your_life": "حياتكِ",
            "your_energy": "طاقتكِ",
            "owner": "صاحبة الخريطة",
        }
    return {
        "you": "أنتَ",
        "can": "تستطيع",
        "need": "تحتاج",
        "have": "لديك",
        "appear": "تظهر",
        "carry": "تحمل",
        "benefit": "تستفيد",
        "watch": "تنتبه",
        "your_chart": "خريطتك",
        "your_self": "نفسك",
        "your_life": "حياتك",
        "your_energy": "طاقتك",
        "owner": "صاحب الخريطة",
    }


def personalize_text(text: str, gender: str) -> str:
    """
    تحويل آمن ومحدود في بدايات الجمل فقط.
    لا نستبدل كلمات مثل: الشخصية، وجوده، أثره... حتى لا تظهر أخطاء لغوية.
    """
    w = gender_words(gender)
    female = gender == "أنثى"

    replacements_start = [
        ("يمتلك ", "تمتلكين " if female else "تمتلك "),
        ("لديه ", "لديكِ " if female else "لديك "),
        ("فيه ", "فيكِ " if female else "فيكَ "),
        ("يحتاج إلى ", "تحتاجين إلى " if female else "تحتاج إلى "),
        ("قد يميل ", "قد تميلين " if female else "قد تميل "),
        ("قد يشعر ", "قد تشعرين " if female else "قد تشعر "),
        ("نخشى عليه ", "نخشى عليكِ " if female else "نخشى عليكَ "),
    ]

    for old, new in replacements_start:
        if text.startswith(old):
            text = new + text[len(old):]

    return text


def personalize_list(items: List[str], gender: str) -> List[str]:
    return [personalize_text(x, gender) for x in items]


HOUSE_MEANINGS = {
    1: "الشخصية، المظهر، طريقة البدء، الجسد، والانطباع الأول.",
    2: "المال، الثقة بالنفس، القيم، الممتلكات، وطريقة التعامل مع الموارد.",
    3: "التفكير، الكلام، الدراسة الأولى، الإخوة، التنقلات القصيرة، وطريقة تبادل المعلومات.",
    4: "العائلة، الجذور، البيت، الذاكرة الداخلية، والأمان النفسي.",
    5: "الحب، الأبناء، الإبداع، المتعة، الهوايات، وطريقة إظهار الفرح.",
    6: "الصحة اليومية، العمل الروتيني، الخدمة، الالتزامات، والعادات المتكررة.",
    7: "الزواج، الشراكات، العلاقات المباشرة، الخصوم، وطريقة التعامل مع الآخر.",
    8: "التحولات، الأزمات، المال المشترك، الخوف العميق، والقدرة على التجدد.",
    9: "السفر، التعليم العالي، الدين، الفلسفة، القانون، والرؤية الواسعة للحياة.",
    10: "المهنة، السمعة، المكانة، الطموح، والظهور أمام المجتمع.",
    11: "الأصدقاء، الجماعات، الدعم الاجتماعي، الأمنيات، والمشاريع المستقبلية.",
    12: "العزلة، الأسرار، اللاوعي، التعب الخفي، الروحانية، وما يعمل خلف الكواليس.",
}

PLANET_MEANINGS = {
    "Sun": "الهوية والإرادة والوعي والقدرة على الظهور.",
    "Moon": "النفس والمشاعر والذاكرة والاحتياج إلى الأمان.",
    "Mercury": "التفكير والكلام والتعلم وطريقة فهم المعلومات.",
    "Venus": "الحب والقبول والجمال والذوق والمال اللطيف.",
    "Mars": "الفعل والشجاعة والغضب والرغبة وطريقة المواجهة.",
    "Jupiter": "التوسع والفرص والمعرفة والثقة والنمو.",
    "Saturn": "المسؤولية والحدود والصبر والتأخير والنضج.",
    "Uranus": "التحرر والمفاجآت والاستقلال والتغيير غير المتوقع.",
    "Neptune": "الخيال والروحانية والإلهام والغموض والضبابية.",
    "Pluto": "التحول العميق والسيطرة والقوة الداخلية وإعادة البناء.",
}

# ============================================================
# دستورية الكواكب في الأبراج والبيوت
# مستخرجة من منهج: Home / Fall / Detriment / Exaltation
# مع قوة وضعف البيت كما في الصور المرفقة.
# ============================================================

PLANET_CONSTITUTION = {
    "Sun": {
        "home": ["الأسد"],
        "exaltation": ["الحمل"],
        "detriment": ["الدلو"],
        "fall": ["الميزان"],
        "strong_houses": [9, 10, 11],
        "weak_houses": [3, 4, 5],
        "notes": "الشمس تقوى عندما تجد مجالًا للظهور والقيادة والمعنى، وتضعف عندما تُحاصر الهوية أو تصبح القيمة الذاتية مرتبطة برضا الآخرين."
    },
    "Moon": {
        "home": ["السرطان"],
        "exaltation": ["الثور"],
        "detriment": ["الجدي"],
        "fall": ["العقرب"],
        "strong_houses": [2, 4],
        "weak_houses": [6, 8, 10, 12],
        "notes": "القمر يقوى حيث يوجد أمان واحتواء واستقرار نفسي، ويضعف عندما تُضغط المشاعر أو تُجبر على الكتمان أو العمل تحت توتر دائم."
    },
    "Mercury": {
        "home": ["الجوزاء", "العذراء"],
        "exaltation": ["الدلو"],
        "detriment": ["القوس", "الحوت"],
        "fall": ["الأسد"],
        "strong_houses": [1, 2],
        "weak_houses": [7, 8, 12],
        "notes": "عطارد يقوى عندما يجد وضوحًا في التفكير والكلام والتجارة والتعلّم، ويضعف عندما يدخل في غموض أو تشويش أو ردود فعل عاطفية مفرطة."
    },
    "Venus": {
        "home": ["الثور", "الميزان"],
        "exaltation": ["الحوت"],
        "detriment": ["العقرب", "الحمل"],
        "fall": ["العذراء"],
        "strong_houses": [2, 4, 7],
        "weak_houses": [6, 8, 10],
        "notes": "الزهرة تقوى في بيوت القبول والراحة والعلاقة والقيمة، وتضعف عندما تُدفع إلى الضغط أو الواجب أو الصراع أو النقد الزائد."
    },
    "Mars": {
        "home": ["الحمل", "العقرب"],
        "exaltation": ["الجدي"],
        "detriment": ["الميزان", "الثور"],
        "fall": ["السرطان"],
        "strong_houses": [1, 10],
        "weak_houses": [4, 6, 12],
        "notes": "المريخ يقوى عندما يجد هدفًا ومواجهة وإنجازًا، ويضعف عندما تُحبس طاقته في الخفاء أو العائلة أو التعب اليومي بلا تصريف."
    },
    "Jupiter": {
        "home": ["القوس", "الحوت"],
        "exaltation": ["السرطان"],
        "detriment": ["الجوزاء", "العذراء"],
        "fall": ["الجدي"],
        "strong_houses": [1, 4, 9],
        "weak_houses": [6, 7, 8],
        "notes": "المشتري يقوى في المعنى والتعليم والسفر والحماية، ويضعف عندما تُحصر حكمته في تفاصيل ضيقة أو مسؤوليات ثقيلة أو أزمات مشتركة."
    },
    "Saturn": {
        "home": ["الجدي", "الدلو"],
        "exaltation": ["الميزان"],
        "detriment": ["السرطان"],
        "fall": ["الحمل"],
        "strong_houses": [7, 10, 11],
        "weak_houses": [1, 4],
        "notes": "زحل يقوى في المسؤولية والبناء والمكانة والقوانين، ويضعف عندما يضغط على الذات أو الجذور النفسية فيصنع ثقلًا داخليًا."
    },
    "Uranus": {
        "home": ["الدلو"],
        "exaltation": ["العقرب"],
        "detriment": ["الأسد"],
        "fall": ["الثور"],
        "strong_houses": [8, 11],
        "weak_houses": [2, 5],
        "notes": "أورانوس يقوى في التجديد والتحرر والتحولات والجماعات، ويضعف عندما يصطدم بالتملك أو الثبات أو الحاجة إلى أمان مادي جامد."
    },
    "Neptune": {
        "home": ["الحوت"],
        "exaltation": ["السرطان"],
        "detriment": ["العذراء"],
        "fall": ["الجدي"],
        "strong_houses": [4, 12],
        "weak_houses": [6, 10],
        "notes": "نبتون يقوى في الروحانية والخيال والعمق الداخلي، ويضعف عندما يدخل في العمل الصارم أو السمعة أو التفاصيل التي تحتاج وضوحًا حادًا."
    },
    "Pluto": {
        "home": ["العقرب"],
        "exaltation": ["الأسد"],
        "detriment": ["الثور"],
        "fall": ["الدلو"],
        "strong_houses": [5, 8],
        "weak_houses": [2, 11],
        "notes": "بلوتو يقوى في التحول العميق والسيطرة الواعية وإعادة البناء، ويضعف عندما يتجمد في التملك أو صراعات الجماعة أو الخوف من خسارة القيمة."
    },
}



PLANET_PERSONALITY_REFLECTIONS = {
    "Sun": {
        "strong": "انعكاس القوة على الشخصية: إرادة أوضح، ثقة أعلى، قدرة على القيادة، وحاجة طبيعية إلى ترك أثر. إذا نضجت هذه القوة تعطي حضورًا وكرامة واستقلالًا.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر تردد في إثبات الذات، أو ربط القيمة الشخصية برأي الآخرين، أو خوف من الظهور. يحتاج الفرد إلى بناء ثقته خطوة بعد خطوة وعدم انتظار الاعتراف الخارجي دائمًا."
    },
    "Moon": {
        "strong": "انعكاس القوة على الشخصية: حس عاطفي واضح، قدرة على الاحتواء، ذاكرة قوية، واستجابة وجدانية تساعد على فهم الناس. إذا نضجت هذه القوة تعطي أمانًا داخليًا وتعاطفًا عميقًا.",
        "weak": "انعكاس الضعف على الشخصية: قد تظهر حساسية زائدة، تقلب مزاج، كتمان للمشاعر، أو صعوبة في طلب الأمان. يحتاج الفرد إلى التعبير عن مشاعره وعدم حمل العبء النفسي بصمت."
    },
    "Mercury": {
        "strong": "انعكاس القوة على الشخصية: عقل سريع أو منظم، قدرة على التعلم، التحليل، الكلام، الكتابة، وربط المعلومات. إذا نضجت هذه القوة تجعل الفرد مقنعًا وذكيًا في التعامل مع التفاصيل.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر تشتت، قلق ذهني، سوء فهم، أو صعوبة في ترتيب الأفكار. يحتاج الفرد إلى تنظيم التفكير والتأكد من وضوح الكلام قبل إصدار الحكم."
    },
    "Venus": {
        "strong": "انعكاس القوة على الشخصية: ذوق، قبول اجتماعي، قدرة على بناء علاقات لطيفة، حس جمالي، وجذب للراحة أو المال أو المحبة. إذا نضجت هذه القوة تعطي توازنًا في الحب والقيمة.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر خوف من الرفض، تعلق عاطفي، صعوبة في تقدير الذات، أو اضطراب في المال والاختيارات الجمالية. يحتاج الفرد إلى عدم قياس قيمته من خلال قبول الآخرين فقط."
    },
    "Mars": {
        "strong": "انعكاس القوة على الشخصية: شجاعة، مبادرة، جرأة، سرعة في الفعل، وقدرة على الدفاع عن الهدف. إذا نضجت هذه القوة تصنع إنجازًا وقيادة عملية.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر غضب مكبوت، اندفاع غير محسوب، خوف من المواجهة، أو صراع داخلي بين الرغبة والفعل. يحتاج الفرد إلى تصريف الطاقة في عمل واضح أو رياضة أو هدف منظم."
    },
    "Jupiter": {
        "strong": "انعكاس القوة على الشخصية: تفاؤل، ثقة، رغبة في التعلم، قابلية للنمو، وانفتاح على السفر أو التجارب الواسعة. إذا نضجت هذه القوة تعطي حكمة وفرصًا ومعنى.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر تضخيم للوعود، ثقة زائدة أو العكس، تشتت في الاتجاهات، أو صعوبة في رؤية الفرصة بوضوح. يحتاج الفرد إلى موازنة التفاؤل بالخطة الواقعية."
    },
    "Saturn": {
        "strong": "انعكاس القوة على الشخصية: صبر، التزام، قدرة على تحمل المسؤولية، بناء طويل الأمد، واحترام للقوانين والحدود. إذا نضجت هذه القوة تصنع مكانة وثباتًا.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر خوف من الفشل، شعور بالثقل، تأخير، قسوة على الذات، أو تجمد أمام المسؤولية. يحتاج الفرد إلى التعامل مع الوقت كحليف لا كعقوبة."
    },
    "Uranus": {
        "strong": "انعكاس القوة على الشخصية: استقلال، أفكار مختلفة، رغبة في التحرر، قدرة على الابتكار، وعدم الخضوع للنمط التقليدي. إذا نضجت هذه القوة تعطي تجديدًا ووعيًا مستقبليًا.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر تمرد مفاجئ، قطيعة، توتر عصبي، أو صعوبة في الاستقرار. يحتاج الفرد إلى التفريق بين الحرية والهروب من الالتزام."
    },
    "Neptune": {
        "strong": "انعكاس القوة على الشخصية: خيال، حدس، رحمة، حس روحي أو فني، وقدرة على الإلهام. إذا نضجت هذه القوة تعطي بصيرة وعمقًا إنسانيًا.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر ضياع، مثالية زائدة، تعلق بصورة غير واقعية، أو صعوبة في رؤية الحدود. يحتاج الفرد إلى وضوح وحقائق عملية حتى لا يذوب في الوهم."
    },
    "Pluto": {
        "strong": "انعكاس القوة على الشخصية: عمق، قوة داخلية، قدرة على التحول، كشف الخفي، وإعادة البناء بعد الأزمات. إذا نضجت هذه القوة تعطي شخصية مؤثرة وشجاعة في مواجهة الحقيقة.",
        "weak": "انعكاس الضعف على الشخصية: قد يظهر خوف من الفقد، رغبة في السيطرة، شك، أو صراعات قوة داخلية وخارجية. يحتاج الفرد إلى تحويل السيطرة إلى وعي، والخوف إلى قدرة على التجدد."
    },
}


def planet_personality_reflection(key: str, score: int) -> str:
    data = PLANET_PERSONALITY_REFLECTIONS.get(key, {})
    if score >= 20:
        return data.get("strong", "")
    if score <= -20:
        return data.get("weak", "")
    strong = data.get("strong", "")
    weak = data.get("weak", "")
    return (
        "انعكاسه على الشخصية: تأثير هذا الكوكب متوسط، لذلك قد تظهر صفاته الإيجابية عند الوعي والتدريب، "
        "وتظهر تحدياته عند الضغط أو سوء التوجيه. "
        + strong.replace("انعكاس القوة على الشخصية:", "في جانبه الإيجابي:").replace("إذا نضجت هذه القوة", "إذا نضج هذا التأثير")
        + " "
        + weak.replace("انعكاس الضعف على الشخصية:", "وفي جانبه الذي يحتاج وعيًا:").replace("يحتاج الفرد", "لذلك يحتاج الفرد")
    )


def planet_sign_dignity(key: str, sign: str) -> Dict[str, object]:
    data = PLANET_CONSTITUTION.get(key, {})
    score = 0
    status = "حيادي"
    text = "لا يظهر للكوكب حكم دستوري خاص في هذا البرج، لذلك تُقرأ قوته من البيت والحد والاتصالات."

    if sign in data.get("home", []):
        score = 30
        status = "موطن"
        text = "الكوكب في موطنه، وهذا يعطيه قدرة طبيعية على التعبير عن دلالته بصورة أوضح وأكثر أصالة."
    elif sign in data.get("exaltation", []):
        score = 25
        status = "شرف / تمجيد"
        text = "الكوكب في موضع شرف أو تمجيد، فيعمل بقوة عالية لكن يحتاج إلى توجيه حتى لا يبالغ في دلالته."
    elif sign in data.get("detriment", []):
        score = -25
        status = "وبال / تضرر"
        text = "الكوكب في موضع وبال أو تضرر، فلا يفقد معناه لكنه يحتاج إلى وعي أكبر حتى لا يظهر بصورة معاكسة لطبيعته."
    elif sign in data.get("fall", []):
        score = -30
        status = "هبوط"
        text = "الكوكب في موضع هبوط، وهذا لا يعني العجز، بل يعني أن دلالته تحتاج إلى تدريب وتهذيب قبل أن تعمل بسهولة."

    return {"status": status, "score": score, "text": text}


def planet_house_strength(key: str, house: int) -> Dict[str, object]:
    data = PLANET_CONSTITUTION.get(key, {})
    score = 0
    status = "متوسط"
    text = "هذا البيت لا يقوّي الكوكب ولا يضعفه بصورة حاسمة، لذلك نرجع إلى البرج والحد والاتصالات."

    if house in data.get("strong_houses", []):
        score = 20
        status = "قوي في البيت"
        text = "موقع الكوكب في هذا البيت يدعم طبيعته ويجعل أثره أوضح في حياة الشخص."
    elif house in data.get("weak_houses", []):
        score = -20
        status = "ضعيف في البيت"
        text = "موقع الكوكب في هذا البيت لا ينسجم بسهولة مع طبيعته، لذلك يحتاج إلى وعي وتنظيم حتى لا يتحول إلى ضغط."

    return {"status": status, "score": score, "text": text}


def planet_constitution_analysis(key: str, p: BodyPosition) -> Dict[str, object]:
    sign_eval = planet_sign_dignity(key, p.sign)
    house_eval = planet_house_strength(key, int(p.house or 0))
    total = int(sign_eval["score"]) + int(house_eval["score"])

    if total >= 40:
        level = "قوي جدًا"
    elif total >= 20:
        level = "قوي"
    elif total > -20:
        level = "متوسط"
    elif total > -40:
        level = "ضعيف ويحتاج إلى وعي"
    else:
        level = "ضعيف جدًا ويحتاج إلى معالجة واعية"

    base_note = PLANET_CONSTITUTION.get(key, {}).get("notes", "")

    reflection = planet_personality_reflection(key, total)

    text = (
        f"دستوريًا: {p.name_ar} في {p.sign} = {sign_eval['status']}، "
        f"وفي البيت {p.house} = {house_eval['status']}. "
        f"التقييم العام: {level} بدرجة {total}. "
        f"{sign_eval['text']} {house_eval['text']} {base_note} "
        f"{reflection}"
    )

    return {"level": level, "score": total, "text": text, "reflection": reflection}



SIGN_SIMPLE_TRAITS = {
    "الحمل": "طاقة مباشرة، مبادرة، سريعة الاستجابة، وتحتاج إلى هدف واضح حتى لا تتحول إلى اندفاع.",
    "الثور": "طاقة ثابتة وعملية، تبحث عن الأمان والنتائج الملموسة، وتحتاج إلى المرونة أمام التغيير.",
    "الجوزاء": "طاقة ذهنية متحركة، تحب المعرفة والكلام والتنوع، وتحتاج إلى التركيز حتى لا تتشتت.",
    "السرطان": "طاقة عاطفية حامية، مرتبطة بالأمان والعائلة والذاكرة، وتحتاج إلى عدم المبالغة في الحساسية.",
    "الأسد": "طاقة حضور وكرامة وإبداع، تحب التأثير والاعتراف، وتحتاج إلى توازن بين الفخر والتواضع.",
    "العذراء": "طاقة تحليل وخدمة وتنظيم، ترى التفاصيل بسرعة، وتحتاج إلى عدم إنهاك نفسها بالنقد والمثالية.",
    "الميزان": "طاقة توازن وعلاقات وذوق، تبحث عن العدل والانسجام، وتحتاج إلى حسم القرار بدل إرضاء الجميع.",
    "العقرب": "طاقة عميقة وقوية وحدسية، تدخل إلى جوهر الأمور، وتحتاج إلى تخفيف الشك أو السيطرة.",
    "القوس": "طاقة توسع ومعرفة وسفر، تبحث عن المعنى والحرية، وتحتاج إلى ربط الحماس بخطة واقعية.",
    "الجدي": "طاقة مسؤولية وبناء وطموح، تنجح بالتدرج، وتحتاج إلى عدم القسوة على الذات.",
    "الدلو": "طاقة استقلال وفكر مختلف، تهتم بالجماعة والمستقبل، وتحتاج إلى عدم الانفصال عن العاطفة.",
    "الحوت": "طاقة حدس وخيال ورحمة، تلتقط ما وراء الظاهر، وتحتاج إلى حدود واضحة حتى لا تذوب في الآخرين.",
}

TERM_INTERPRETATION = {
    "الشمس": "الحد الشمسي يضيف رغبة في الظهور والوضوح والثقة، ويجعل الدلالة تميل إلى إثبات الذات.",
    "القمر": "الحد القمري يضيف حساسية واستجابة شعورية، ويجعل الدلالة مرتبطة بالأمان والانفعال الداخلي.",
    "عطارد": "حد عطارد يضيف تفكيرًا وتحليلًا وكلامًا وحركة ذهنية، ويجعل الدلالة عقلية أو تواصلية.",
    "الزهرة": "حد الزهرة يضيف لينًا وقبولًا وذوقًا، ويجعل الدلالة أقرب إلى العلاقات أو الجمال أو التهدئة.",
    "المريخ": "حد المريخ يضيف حرارة واندفاعًا ومواجهة، ويحتاج إلى وعي حتى لا يتحول إلى توتر.",
    "المشتري": "حد المشتري يضيف توسعًا وثقة وفرصة، ويجعل الدلالة قابلة للنمو إذا استُخدمت بحكمة.",
    "زحل": "حد زحل يضيف جدية وتأخيرًا ومسؤولية، ويطلب الصبر والتنظيم قبل ظهور النتائج.",
}


def aspect_sentence_for_planet(planet_ar: str, aspects) -> str:
    related = []
    for a, b, asp, orb in aspects:
        if a == planet_ar:
            related.append(f"{asp} {b}")
        elif b == planet_ar:
            related.append(f"{asp} {a}")
    if not related:
        return "لا تظهر له اتصالات رئيسية قوية ضمن الأورب المعتمد في هذه النسخة، لذلك تُقرأ دلالته أساسًا من البرج والبيت والحد."
    return "أبرز اتصالاته: " + "، ".join(related[:4]) + "."


def planet_reading_text(key: str, p: BodyPosition, aspects) -> str:
    planet_meaning = PLANET_MEANINGS.get(key, "")
    sign_trait = SIGN_SIMPLE_TRAITS.get(p.sign, "")
    term_text = TERM_INTERPRETATION.get(p.term or "", "")
    retro = " وهو متراجع، لذلك تعمل دلالته بطريقة داخلية أو مراجِعة وتحتاج إلى وقت قبل التعبير الواضح." if p.retrograde else ""
    asp_text = aspect_sentence_for_planet(p.name_ar, aspects)
    constitution = planet_constitution_analysis(key, p)

    return (
        f"{p.name_ar}: يمثل {planet_meaning} وجوده في {p.sign} يعطي {sign_trait} "
        f"وموقعه في البيت {p.house} يربط هذه الطاقة بموضوع: {HOUSE_MEANINGS.get(p.house, '')} "
        f"ويقع عند {format_degree(p.degree)} من {p.sign} ضمن حد {p.term}. "
        f"هنا لا نقرأ {p.name_ar} من البرج والبيت فقط، بل ندمج الحد أيضًا؛ {term_text} "
        f"{constitution['text']} "
        f"{retro} {asp_text}"
    )


def house_reading_text(house_num: int, cusp_lon: float, positions) -> str:
    sign, degree = sign_from_lon(cusp_lon)
    ruler = SIGN_RULERS.get(sign, "")
    planets_inside = [p.name_ar for p in positions.values() if p.house == house_num]
    planets_text = " وفيه: " + "، ".join(planets_inside) + "." if planets_inside else " ولا توجد فيه كواكب أساسية، لذلك يُقرأ من البرج الحاكم وحاكم البيت."
    term = get_ptolemy_term(sign, degree)
    term_text = TERM_INTERPRETATION.get(term, "")
    return (
        f"البيت {house_num}: يبدأ في {sign} عند {format_degree(degree)}، ومعناه العام: {HOUSE_MEANINGS[house_num]} "
        f"حاكم هذا البيت هو {ruler}. بداية البيت تقع في حد {term}، وهذا يضيف طبقة تفسيرية إلى معنى البيت؛ {term_text}{planets_text}"
    )


def generate_general_analysis(name: str, positions, angles, element_scores) -> str:
    asc_sign = str(angles["ASC_sign"])
    sun = positions["Sun"]
    moon = positions["Moon"]
    dominant = strongest_element(element_scores)
    asc_ruler = SIGN_RULERS.get(asc_sign, "")

    dominant_text = {
        "نار": "يغلب على الخريطة عنصر النار، وهذا يعطي رغبة في الحركة والمبادرة والتعبير المباشر عن الذات.",
        "تراب": "يغلب على الخريطة عنصر التراب، وهذا يدل على عقلية عملية تبحث عن الثبات والإنجاز والنتائج المحسوسة.",
        "هواء": "يغلب على الخريطة عنصر الهواء، وهذا يشير إلى عقل نشط وتواصل قوي واهتمام بالأفكار والعلاقات الذهنية.",
        "ماء": "يغلب على الخريطة عنصر الماء، وهذا يكشف حساسية وحدسًا وعمقًا نفسيًا وقدرة على التقاط ما وراء الكلام."
    }.get(dominant, "")

    return (
        f"الخريطة العامة لـ {name} تقوم على تفاعل مهم بين الطالع في {asc_sign}، والشمس في {sun.sign}، والقمر في {moon.sign}. "
        f"الطالع يوضح طريقة الدخول إلى الحياة والتعامل الأول مع الناس، والشمس تكشف الإرادة والهوية، والقمر يصف النفس الداخلية والحاجة العاطفية. "
        f"{dominant_text} حاكم الطالع هو {asc_ruler}، لذلك يجب متابعته لأنه يمثل مفتاح الحركة الشخصية واتجاه النمو في الحياة. "
        "هذه القراءة لا تتعامل مع الإنسان كصفة واحدة، بل كتركيب متداخل بين الإرادة والمشاعر والعقل والعمل والعلاقات."
    )


def generate_asc_sun_moon_analysis(positions, angles) -> Dict[str, str]:
    asc_sign = str(angles["ASC_sign"])
    asc_degree = float(angles["ASC_degree"])
    asc_term = get_ptolemy_term(asc_sign, asc_degree)
    asc_ruler = SIGN_RULERS.get(asc_sign, "")

    sun = positions["Sun"]
    moon = positions["Moon"]

    asc_text = (
        f"الطالع في {asc_sign} عند {format_degree(asc_degree)} ضمن حد {asc_term}. "
        f"هذا يصف طريقة ظهور الشخص وبدايته مع الحياة. {SIGN_SIMPLE_TRAITS.get(asc_sign, '')} "
        f"حاكم الطالع هو {asc_ruler}، ولذلك يصبح هذا الحاكم مفتاحًا مهمًا في فهم اتجاه الشخصية ونمط استجابتها."
    )

    sun_text = (
        f"الشمس في {sun.sign} في البيت {sun.house} عند {format_degree(sun.degree)} ضمن حد {sun.term}. "
        f"الشمس تمثل الهوية والإرادة والوعي. {SIGN_SIMPLE_TRAITS.get(sun.sign, '')} "
        f"وجودها في البيت {sun.house} يجعل موضوع {HOUSE_MEANINGS.get(sun.house, '')} مجالًا مهمًا لإثبات الذات وبناء الثقة."
    )

    moon_text = (
        f"القمر في {moon.sign} في البيت {moon.house} عند {format_degree(moon.degree)} ضمن حد {moon.term}. "
        f"القمر يمثل النفس والمشاعر والاحتياج إلى الأمان. {SIGN_SIMPLE_TRAITS.get(moon.sign, '')} "
        f"وجوده في البيت {moon.house} يجعل موضوع {HOUSE_MEANINGS.get(moon.house, '')} مؤثرًا في المزاج الداخلي والراحة النفسية."
    )

    return {"asc": asc_text, "sun": sun_text, "moon": moon_text}


def generate_planetary_analysis(positions, aspects) -> List[str]:
    order = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
    return [planet_reading_text(k, positions[k], aspects) for k in order]


def generate_houses_analysis(cusps, positions) -> List[str]:
    return [house_reading_text(i + 1, cusps[i], positions) for i in range(12)]




def modality_scores(positions: Dict[str, BodyPosition]) -> Dict[str, int]:
    modes = {
        "الحمل": "مبادر", "السرطان": "مبادر", "الميزان": "مبادر", "الجدي": "مبادر",
        "الثور": "ثابت", "الأسد": "ثابت", "العقرب": "ثابت", "الدلو": "ثابت",
        "الجوزاء": "متغير", "العذراء": "متغير", "القوس": "متغير", "الحوت": "متغير",
    }
    weights = {
        "Sun": 3, "Moon": 3, "Mercury": 2, "Venus": 2,
        "Mars": 2, "Jupiter": 1, "Saturn": 1
    }
    scores = {"مبادر": 0, "ثابت": 0, "متغير": 0}
    for key, weight in weights.items():
        scores[modes[positions[key].sign]] += weight
    return scores



MIDPOINT_GROUPS = {
    "عاطفيًا": [
        ("الشمس/الزهرة", "Sun", "Venus", "نقطة جاذبية وذوق ومحبة، وتوضح طريقة إظهار القبول والجمال والعاطفة الهادئة."),
        ("القمر/الزهرة", "Moon", "Venus", "نقطة عاطفية رقيقة تكشف الاحتياج إلى الحنان والقبول والراحة النفسية في العلاقات."),
        ("الزهرة/المريخ", "Venus", "Mars", "نقطة الرغبة والجاذبية والحركة العاطفية، وتوضح كيف تمتزج العاطفة بالفعل والرغبة."),
        ("القمر/المريخ", "Moon", "Mars", "نقطة الانفعال العاطفي ورد الفعل، وقد تكشف سرعة التأثر أو الحماس أو الغضب العاطفي."),
        ("الطالع/الزهرة", "ASC", "Venus", "نقطة القبول الشخصي والجاذبية الظاهرة، وتفيد في فهم الطريقة التي يُستقبل بها الشخص عاطفيًا واجتماعيًا."),
    ],
    "مهنيًا": [
        ("الشمس/المريخ", "Sun", "Mars", "نقطة الإرادة والفعل، وتكشف قوة المبادرة والقدرة على الدفاع عن الهدف."),
        ("الشمس/زحل", "Sun", "Saturn", "نقطة المسؤولية والالتزام وبناء المكانة، وتوضح أين يحتاج النجاح إلى صبر وهيكلة."),
        ("الشمس/المشتري", "Sun", "Jupiter", "نقطة التوسع والطموح والثقة، وقد تشير إلى قابلية النمو المهني عند حسن استثمار الفرصة."),
        ("زحل/المريخ", "Saturn", "Mars", "نقطة الضغط بين الفعل والحدود، وتحتاج إلى ضبط الغضب والصبر في الإنجاز والعمل."),
        ("العاشر/الشمس", "MC", "Sun", "نقطة الظهور والسمعة والهوية المهنية، وتكشف علاقة الإرادة الشخصية بالمكانة العامة."),
    ],
    "ماليًا": [
        ("الزهرة/المشتري", "Venus", "Jupiter", "نقطة الوفرة والقبول المالي والفرص السهلة، وتدل على مواضع الاستفادة إذا وُجد وعي بالفرصة."),
        ("الزهرة/زحل", "Venus", "Saturn", "نقطة المال المنظم والحذر المالي، وقد تدل على كسب يأتي بعد تأخير أو مسؤولية."),
        ("المشتري/زحل", "Jupiter", "Saturn", "نقطة التوازن بين التوسع والحدود، وهي مهمة في إدارة المال والاستثمار طويل المدى."),
        ("المريخ/المشتري", "Mars", "Jupiter", "نقطة الجرأة المالية والمخاطرة المحسوبة، وتحتاج إلى خطة حتى لا تتحول إلى اندفاع."),
        ("الثاني/الزهرة", "CUSP2", "Venus", "نقطة الموارد والقيمة الشخصية والقدرة على جذب المال أو تحسين الدخل."),
    ],
    "الدراسة والتفكير": [
        ("عطارد/الزهرة", "Mercury", "Venus", "نقطة الكلام الجميل والذوق في التعبير، وتفيد في الكتابة، الإقناع، الفن، والتعليم اللطيف."),
        ("عطارد/المشتري", "Mercury", "Jupiter", "نقطة المعرفة والسفر والتوسع الذهني، وتفيد في التعليم، التجارة، اللغات، والرؤية الواسعة."),
        ("عطارد/زحل", "Mercury", "Saturn", "نقطة التفكير الجاد والمنهجي، وتفيد في الدراسة العميقة والبحث والتنظيم."),
        ("عطارد/أورانوس", "Mercury", "Uranus", "نقطة الذكاء المفاجئ والأفكار المختلفة، وتفيد في التقنية والابتكار والتحليل السريع."),
        ("الثالث/عطارد", "CUSP3", "Mercury", "نقطة الدراسة الأولى والتواصل والكتابة والتنقلات القصيرة."),
    ],
    "السفر والتوسع": [
        ("المشتري/عطارد", "Jupiter", "Mercury", "نقطة السفر والمعرفة واللغات والتبادل الفكري، وهي من أهم نقاط الحركة الذهنية والجغرافية."),
        ("المشتري/الشمس", "Jupiter", "Sun", "نقطة الرؤية الواسعة والثقة والانفتاح على تجارب أكبر من البيئة المعتادة."),
        ("المشتري/القمر", "Jupiter", "Moon", "نقطة الراحة في التوسع وتغيير المكان، وقد تعطي قابلية نفسية للاستفادة من السفر أو الانتقال."),
        ("التاسع/المشتري", "CUSP9", "Jupiter", "نقطة السفر البعيد والتعليم العالي والرؤية الفلسفية أو الدينية."),
        ("التاسع/عطارد", "CUSP9", "Mercury", "نقطة الدراسة العليا واللغات والتواصل مع بيئات مختلفة."),
    ],
}


def get_point_lon(key: str, positions: Dict[str, BodyPosition], cusps: List[float], angles: Dict[str, float]) -> float:
    """
    تحويل اسم النقطة إلى طول فلكي.
    يدعم الكواكب، الطالع، العاشر، وبعض رؤوس البيوت.
    """
    if key in positions:
        return float(positions[key].lon)
    if key == "ASC":
        return float(angles["ASC"])
    if key == "MC":
        return float(angles["MC"])
    if key.startswith("CUSP"):
        house_num = int(key.replace("CUSP", ""))
        return float(cusps[house_num - 1])
    raise ValueError(f"نقطة غير معروفة: {key}")


def midpoint_short_arc(lon1: float, lon2: float) -> float:
    """
    حساب نقطة المنتصف على القوس الأقصر.
    """
    a = normalize_deg(lon1)
    b = normalize_deg(lon2)
    diff = normalize_deg(b - a)
    if diff > 180:
        diff -= 360
    return normalize_deg(a + diff / 2.0)


def midpoint_activation_text(mid_lon: float, positions: Dict[str, BodyPosition], orb: float = 2.0) -> str:
    """
    فحص تفعيل نقطة المنتصف من كواكب الميلاد بالاقتران/التربيع/المقابلة.
    """
    hits = []
    for p in positions.values():
        d0 = angular_distance(mid_lon, p.lon)
        d90 = abs(angular_distance(mid_lon, p.lon) - 90)
        d180 = abs(angular_distance(mid_lon, p.lon) - 180)

        if d0 <= orb:
            hits.append(f"{p.name_ar} يقترن بها")
        elif d90 <= orb:
            hits.append(f"{p.name_ar} يربعها")
        elif d180 <= orb:
            hits.append(f"{p.name_ar} يقابلها")

    if hits:
        return " وهي مفعّلة في الخريطة عبر: " + "، ".join(hits[:4]) + "."
    return " ولا يظهر عليها تفعيل قوي من كواكب الميلاد ضمن أورب درجتين، لكنها تبقى نقطة حساسة عند العبور أو التقدم."


def midpoint_priority_score(mid_lon: float, house: int, term: str, positions: Dict[str, BodyPosition]) -> int:
    """
    درجة بسيطة لترتيب نقاط المنتصف داخل كل موضوع.
    """
    score = 0

    if house in [1, 4, 7, 10]:
        score += 25
    elif house in [2, 5, 8, 9, 11]:
        score += 15
    else:
        score += 8

    if term in ["الشمس", "القمر", "الزهرة", "المشتري"]:
        score += 12
    elif term in ["عطارد", "المريخ"]:
        score += 8
    elif term == "زحل":
        score += 6

    for p in positions.values():
        d0 = angular_distance(mid_lon, p.lon)
        d90 = abs(angular_distance(mid_lon, p.lon) - 90)
        d180 = abs(angular_distance(mid_lon, p.lon) - 180)
        if d0 <= 2 or d90 <= 2 or d180 <= 2:
            score += 25
            break

    return score


def midpoint_item_text(label: str, a_key: str, b_key: str, meaning: str, positions, cusps, angles) -> Dict[str, object]:
    lon1 = get_point_lon(a_key, positions, cusps, angles)
    lon2 = get_point_lon(b_key, positions, cusps, angles)
    mid_lon = midpoint_short_arc(lon1, lon2)
    sign, degree = sign_from_lon(mid_lon)
    house = house_from_cusps(mid_lon, cusps)
    term = get_ptolemy_term(sign, degree)
    activation = midpoint_activation_text(mid_lon, positions)
    score = midpoint_priority_score(mid_lon, house, term, positions)

    text = (
        f"نقطة {label} تقع في {sign} عند {format_degree(degree)} في البيت {house} وضمن حد {term}. "
        f"{meaning} "
        f"وجودها في البيت {house} يربطها بموضوع: {HOUSE_MEANINGS.get(house, '')} "
        f"أما حد {term} فيعطيها النوعية التالية: {TERM_INTERPRETATION.get(term, '')} "
        f"{activation}"
    )

    return {"text": text, "score": score}


def generate_midpoints_analysis(positions, cusps, angles) -> List[Dict[str, object]]:
    """
    تحليل نقاط المنتصف حسب الموضوعات:
    عاطفية، مهنية، مالية، دراسة وتفكير، سفر وتوسع.
    """
    groups: List[Dict[str, object]] = []

    for group_title, definitions in MIDPOINT_GROUPS.items():
        items = []
        for label, a_key, b_key, meaning in definitions:
            try:
                items.append(midpoint_item_text(label, a_key, b_key, meaning, positions, cusps, angles))
            except Exception:
                continue

        # ترتيب النقاط داخل كل محور حسب الأهمية لا حسب الإدخال فقط
        items.sort(key=lambda x: int(x["score"]), reverse=True)

        groups.append({
            "title": group_title,
            "items": [x["text"] for x in items]
        })

    return groups


def generate_terms_analysis(positions, angles) -> List[str]:
    """
    تحليل حدود بطليموس كقسم مستقل.
    """
    items: List[str] = []

    asc_sign = str(angles["ASC_sign"])
    asc_degree = float(angles["ASC_degree"])
    asc_term = get_ptolemy_term(asc_sign, asc_degree)
    items.append(
        f"الطالع يقع في حد {asc_term}. {TERM_INTERPRETATION.get(asc_term, '')} "
        "لذلك لا نقرأ الطالع من البرج فقط، بل من نوعية الحد أيضًا؛ فالحد يوضح طريقة خروج الطاقة إلى الحياة."
    )

    for key in ["Sun", "Moon", "Mercury", "Venus", "Mars"]:
        p = positions[key]
        items.append(
            f"{p.name_ar} في حد {p.term}: {TERM_INTERPRETATION.get(p.term or '', '')} "
            f"هذا يلوّن دلالة {p.name_ar} داخل {p.sign} ويجعل أثره في البيت {p.house} أكثر تحديدًا."
        )

    return items


def generate_supporting_techniques(positions, cusps, angles, aspects, element_scores) -> List[str]:
    """
    قسم يضم التقنيات التي اتفقنا على عدم إهمالها في V1:
    العناصر، الطبائع، الزوايا، البيوت الزاوية، حكام البيوت، الحدود.
    التقنيات الزمنية مثل التقدم والقوس الشمسي والعودة الشمسية تؤجل لنسخة التوقعات.
    """
    items: List[str] = []

    dominant_element = strongest_element(element_scores)
    items.append(
        f"العنصر الغالب هو {dominant_element}. هذا يحدد المزاج العام للطاقة: "
        "النار تدفع للمبادرة، التراب للبناء العملي، الهواء للفكر والتواصل، والماء للحدس والشعور."
    )

    modes = modality_scores(positions)
    dominant_mode = max(modes, key=lambda k: modes[k])
    mode_text = {
        "مبادر": "غلبة الطبيعة المبادرة تعني أن الطاقة تتحرك عبر البدء وفتح المسارات، لكنها تحتاج إلى إكمال ما تبدأه.",
        "ثابت": "غلبة الطبيعة الثابتة تعني قدرة على الصبر والاستمرار، لكنها تحتاج إلى مرونة أمام التغيير.",
        "متغير": "غلبة الطبيعة المتغيرة تعني قابلية للتكيّف والفهم السريع، لكنها تحتاج إلى تقليل التشتت."
    }
    items.append(f"الطبيعة الغالبة هي {dominant_mode}. {mode_text.get(dominant_mode, '')}")

    # البيوت الزاوية
    angular_planets = []
    for p in positions.values():
        if p.house in [1, 4, 7, 10]:
            angular_planets.append(f"{p.name_ar} في البيت {p.house}")
    if angular_planets:
        items.append(
            "الكواكب الموجودة في البيوت الزاوية تعطي تأثيرًا ظاهرًا وقويًا في الحياة. "
            "في هذه الخريطة يظهر: " + "، ".join(angular_planets[:8]) + "."
        )
    else:
        items.append(
            "لا توجد كواكب كثيرة في البيوت الزاوية، لذلك قد تعمل الشخصية بطريقة داخلية أو تدريجية أكثر من الظهور المباشر."
        )

    # حكام المحاور
    asc_sign = str(angles["ASC_sign"])
    desc_lon = normalize_deg(float(angles["ASC"]) + 180)
    desc_sign, desc_deg = sign_from_lon(desc_lon)
    mc_sign = str(angles["MC_sign"])
    ic_lon = normalize_deg(float(angles["MC"]) + 180)
    ic_sign, ic_deg = sign_from_lon(ic_lon)

    items.append(
        f"محور الأول والسابع: الطالع في {asc_sign} وحاكمه {SIGN_RULERS.get(asc_sign, '')}، "
        f"والهابط في {desc_sign} وحاكمه {SIGN_RULERS.get(desc_sign, '')}. "
        "هذا المحور يشرح التوازن بين الذات والآخر، وبين المبادرة الشخصية ونوع العلاقات التي تجذبها الخريطة."
    )

    items.append(
        f"محور الرابع والعاشر: الرابع في {ic_sign} وحاكمه {SIGN_RULERS.get(ic_sign, '')}، "
        f"والعاشر في {mc_sign} وحاكمه {SIGN_RULERS.get(mc_sign, '')}. "
        "هذا المحور يوضح العلاقة بين الجذور والعائلة من جهة، والطموح والسمعة والمهنة من جهة أخرى."
    )

    # الزوايا
    hard = [x for x in aspects if x[2] in ["تربيع", "مقابلة"]]
    soft = [x for x in aspects if x[2] in ["تثليث", "تسديس"]]
    conj = [x for x in aspects if x[2] == "اقتران"]

    if conj:
        items.append(
            "الاقترانات في الخريطة تعمل كمراكز تركيز قوية، لأنها تجمع طاقتين في نقطة واحدة. "
            "أبرزها: " + "، ".join([f"{a} مع {b}" for a, b, asp, orb in conj[:5]]) + "."
        )
    if hard:
        items.append(
            "التربيعات والمقابلات تمثل مناطق ضغط وتحدٍّ، لكنها أيضًا مناطق نضج وإنجاز إذا وُجهت بوعي. "
            "أبرزها: " + "، ".join([f"{a} {asp} {b}" for a, b, asp, orb in hard[:5]]) + "."
        )
    if soft:
        items.append(
            "التثليثات والتسديسات تمثل مواهب ومنافذ مساعدة، لكنها تحتاج إلى استخدام فعلي حتى لا تبقى طاقة كامنة. "
            "أبرزها: " + "، ".join([f"{a} {asp} {b}" for a, b, asp, orb in soft[:5]]) + "."
        )

    # ملاحظة تقنية زمنية
    items.append(
        "التقنيات الزمنية مثل التقدم الثانوي، القوس الشمسي، العودة الشمسية، العودة القمرية، البروفكشن والفريدار "
        "ليست مهملة، لكنها تُستخدم عند طلب توقيت أو توقع لفترة محددة، أما هنا فالمحور الأساسي هو قراءة الميلاد."
    )

    return items


def generate_dignity_summary(positions: Dict[str, BodyPosition]) -> List[str]:
    """
    خلاصة مرتبة لقوة الكواكب حسب الدستورية، مع انعكاسها على الشخصية.
    """
    rows = []
    key_by_name = {}
    for key in ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]:
        p = positions[key]
        info = planet_constitution_analysis(key, p)
        rows.append((int(info["score"]), p.name_ar, info["level"], p.sign, p.house, key, info["reflection"]))
        key_by_name[p.name_ar] = key

    rows.sort(key=lambda x: x[0], reverse=True)

    strongest = rows[:3]
    weakest = rows[-3:]

    items = []
    items.append(
        "أقوى الكواكب دستوريًا في هذه الخريطة: "
        + "، ".join([f"{name} ({level})" for score, name, level, sign, house, key, reflection in strongest])
        + ". انعكاس ذلك على الشخصية أن هذه الكواكب تمثل أدوات طبيعية يمكن الاعتماد عليها في الثقة، الإنجاز، اتخاذ القرار، أو بناء العلاقات بحسب طبيعة كل كوكب."
    )
    items.append(
        "أكثر الكواكب حاجة إلى وعي أو تهذيب: "
        + "، ".join([f"{name} ({level})" for score, name, level, sign, house, key, reflection in weakest])
        + ". انعكاس ذلك لا يعني ضعفًا نهائيًا، بل يدل على مناطق قد يظهر فيها توتر أو تأخير أو حساسية، وتحتاج إلى تدريب وبيئة مناسبة."
    )

    for score, name, level, sign, house, key, reflection in rows:
        items.append(
            f"{name}: {level}، لأنه في {sign} والبيت {house}. الدرجة الدستورية: {score}. {reflection}"
        )

    return items


# ============================================================
# أنماط توزيع الكواكب في الخريطة
# Bundle / Bowl / Bucket / Splash / Seesaw / Locomotive / Splay
# ============================================================

PATTERN_AR_NAMES = {
    "Bundle": "الحزمة",
    "Bowl": "الوعاء",
    "Bucket": "الدلو",
    "Splash": "الرش",
    "Seesaw": "الأرجوحة",
    "Locomotive": "القاطرة",
    "Splay": "التفرّع",
    "Mixed_Seesaw_Splay": "تفرّع مع ميل إلى الأرجوحة",
    "Mixed_Locomotive_Splay": "تفرّع مع ميل إلى القاطرة",
}

PATTERN_MEANINGS = {
    "Bundle": {
        "meaning": "هذا النمط يدل على أن الطاقة مركّزة في مساحة محددة من الخريطة. الشخصية هنا تميل إلى التعمق والتركيز في مجال أو اتجاه واضح.",
        "strength": "قوة هذا النمط في التركيز، العمق، والقدرة على توجيه الجهد نحو موضوع محدد.",
        "challenge": "تحديه أن لا تنحصر الحياة في زاوية واحدة، وأن لا يتحول التركيز إلى انغلاق أو ضيق في الرؤية.",
        "advice": "النصيحة: استفد من قوة التركيز، لكن افتح لنفسك نوافذ جديدة حتى لا تبقى الطاقة محصورة في مجال واحد."
    },
    "Bowl": {
        "meaning": "هذا النمط يدل على أن الكواكب متجمعة في نصف الخريطة تقريبًا، وكأن هناك نصفًا ممتلئًا ونصفًا ينتظر الاكتمال. الشخصية تشعر غالبًا بوجود جانب ناقص تسعى إلى تعويضه أو فهمه.",
        "strength": "قوته في الوعي بما يملكه الفرد وبناء موقف واضح من الحياة.",
        "challenge": "تحديه هو الشعور الداخلي بالنقص أو السعي المستمر نحو الجهة الفارغة من الخريطة.",
        "advice": "النصيحة: لا تنظر إلى الجهة الفارغة كعجز، بل كمساحة نمو وتعلّم وتجربة."
    },
    "Bucket": {
        "meaning": "هذا النمط يدل على أن أغلب الكواكب متجمعة في جهة، مع كوكب منفرد في الجهة المقابلة يعمل مثل مقبض الدلو. هذا الكوكب يصبح مفتاحًا مهمًا في توجيه الحياة.",
        "strength": "قوته في وجود كوكب موجّه يركز طاقة الخريطة ويعطيها بوابة واضحة للتعبير.",
        "challenge": "تحديه أن لا تصبح حياة الفرد كلها معلّقة بموضوع الكوكب المنفرد فقط.",
        "advice": "النصيحة: استخدم الكوكب المقبض كأداة توجيه، لا كعبء أو نقطة تعلق."
    },
    "Splash": {
        "meaning": "هذا النمط يدل على انتشار الكواكب في معظم أجزاء الخريطة. الشخصية متعددة الاهتمامات وقادرة على تجربة أكثر من مجال.",
        "strength": "قوته في التنوع، المرونة، والانفتاح على خبرات مختلفة.",
        "challenge": "تحديه هو التشتت وصعوبة تثبيت الجهد في مسار واحد لفترة كافية.",
        "advice": "النصيحة: اجعل التنوع مصدر غنى، لكن اختر أولويات واضحة حتى لا تتوزع الطاقة بلا نتيجة."
    },
    "Seesaw": {
        "meaning": "هذا النمط يدل على وجود مجموعتين متقابلتين من الكواكب. الحياة تُعاش غالبًا عبر شدّ بين طرفين أو محورين.",
        "strength": "قوته في القدرة على رؤية الجانبين والمقارنة والموازنة.",
        "challenge": "تحديه هو التردد أو الشعور بأنه ممزق بين اتجاهين: الذات والآخر، العمل والعائلة، العقل والعاطفة، أو الحرية والمسؤولية.",
        "advice": "النصيحة: لا تجعل التناقض صراعًا دائمًا؛ حوّله إلى قدرة على التوازن والاختيار الواعي."
    },
    "Locomotive": {
        "meaning": "هذا النمط يدل على انتشار الكواكب في معظم الخريطة مع فراغ كبير واحد، وكأن هناك قوة دفع تتحرك باتجاه واضح.",
        "strength": "قوته في الاندفاع، فتح الطريق، والاستمرار في الحركة نحو هدف.",
        "challenge": "تحديه هو التسرع أو الشعور الدائم بأنه يجب أن يدفع الحياة إلى الأمام.",
        "advice": "النصيحة: حدّد الهدف قبل الاندفاع، لأن قوة القاطرة تصبح أعظم عندما تعرف إلى أين تتجه."
    },
    "Splay": {
        "meaning": "هذا النمط يدل على وجود عدة تجمعات للكواكب بصورة غير منتظمة. الشخصية لها أكثر من مركز اهتمام وقد لا تسير في خط واحد.",
        "strength": "قوته في الأصالة والاستقلال والقدرة على العمل في أكثر من محور.",
        "challenge": "تحديه هو صعوبة جمع المسارات المختلفة في هوية واحدة أو هدف واضح.",
        "advice": "النصيحة: لا تحارب تعدد اهتماماتك، لكن امنحه نظامًا حتى يتحول إلى مشروع واضح."
    },
    "Mixed_Seesaw_Splay": {
        "meaning": "هذا النمط يدل على وجود أكثر من تجمع كوكبي مع شدّ واضح بين جهتين، لكنه لا يصل إلى أرجوحة صافية لأن المجموعات غير متوازنة.",
        "strength": "قوته في القدرة على رؤية أكثر من زاوية، مع تعدد مراكز الاهتمام والخبرة.",
        "challenge": "تحديه هو أن يشعر الفرد بشدّ بين محورين، لكنه في الوقت نفسه لا يملك توازن الأرجوحة الكلاسيكية؛ لذلك قد يتنقل بين أكثر من مركز ضغط أو اهتمام.",
        "advice": "النصيحة: لا تتعامل مع التناقض كصراع دائم، ولا مع التعدد كتشتت؛ اجمع المحاور المختلفة في هدف عملي واضح."
    },
    "Mixed_Locomotive_Splay": {
        "meaning": "هذا النمط يدل على وجود قوة دفع واضحة بسبب فراغ كبير، لكن التوزيع الداخلي للكواكب ليس متصلًا بما يكفي ليكون قاطرة صافية.",
        "strength": "قوته في وجود دافع للتقدم مع أكثر من مركز اهتمام.",
        "challenge": "تحديه هو التذبذب بين الاندفاع نحو هدف وبين التوزع على أكثر من اتجاه.",
        "advice": "النصيحة: حدّد مركز القيادة أولًا، ثم رتّب بقية الاهتمامات حوله حتى لا تتبعثر الطاقة."
    },
}

PLANET_LEADER_MEANINGS = {
    "الشمس": "الكوكب القائد هنا يشير إلى أن الإرادة والهوية والظهور هي بوابة الحركة في الحياة.",
    "القمر": "الكوكب القائد هنا يشير إلى أن الشعور والحاجة إلى الأمان والذاكرة النفسية تقود كثيرًا من الاستجابات.",
    "عطارد": "الكوكب القائد هنا يشير إلى أن التفكير والكلام والتعلم والربط الذهني هي بوابة الحركة.",
    "الزهرة": "الكوكب القائد هنا يشير إلى أن العلاقات والقبول والذوق والمال اللطيف لها دور محوري في توجيه الحياة.",
    "المريخ": "الكوكب القائد هنا يشير إلى أن المبادرة والفعل والمواجهة والجرأة هي مفاتيح أساسية في الشخصية.",
    "المشتري": "الكوكب القائد هنا يشير إلى أن التوسع والمعرفة والسفر والثقة والفرص تقود مسارًا مهمًا في الحياة.",
    "زحل": "الكوكب القائد هنا يشير إلى أن المسؤولية والصبر والبناء والخوف من الفشل أو الرغبة في الإنجاز تشكل محورًا مهمًا.",
    "أورانوس": "الكوكب القائد هنا يشير إلى أن الاستقلال والتغيير والاختلاف والتحرر من النمط التقليدي يوجهان الخريطة.",
    "نبتون": "الكوكب القائد هنا يشير إلى أن الخيال والحدس والروحانية والغموض والإلهام لهم تأثير واضح في الحركة الداخلية.",
    "بلوتو": "الكوكب القائد هنا يشير إلى أن التحول العميق والقوة والسيطرة الواعية وإعادة البناء بعد الأزمات تقود جزءًا مهمًا من الحياة.",
}


PATTERN_LIFE_REFLECTIONS = {
    "Bundle": (
        "الشرح العملي للقارئ: عندما تكون الخريطة من نوع الحزمة فهذا يعني أن الطاقة النفسية والحياتية مركزة في قطاع محدود من الحياة. "
        "صاحب هذه الخريطة غالبًا لا يعيش كل شيء بالتساوي، بل ينشد مجالًا محددًا يغرق فيه أو يتخصص به أو يشعر أنه يمثل مركز حياته. "
        "هذا يعطي قوة تركيز عالية وقدرة على التعمق، لكنه قد يجعل الشخص يرى الحياة من زاوية واحدة فقط. "
        "مفتاح النمو هنا هو توسيع التجربة دون خسارة قوة التركيز."
    ),
    "Bowl": (
        "الشرح العملي للقارئ: نمط الوعاء يعني أن هناك نصفًا ممتلئًا من الخريطة ونصفًا يبدو فارغًا، ولذلك يشعر الشخص غالبًا أن لديه جانبًا قويًا يعرفه جيدًا، "
        "وفي المقابل يوجد جانب آخر يبحث عنه أو يحاول تعويضه. "
        "هذا النمط يعطي وعيًا واضحًا بالذات وبما يملكه الفرد، لكنه قد يخلق شعورًا داخليًا بأن شيئًا ما ناقص أو أن الحياة تطلب منه الوصول إلى الجهة الأخرى. "
        "مفتاح النمو هنا هو عدم التعامل مع الفراغ كضعف، بل كاتجاه تطور."
    ),
    "Bucket": (
        "الشرح العملي للقارئ: نمط الدلو يعني أن الخريطة كلها تقريبًا تصب طاقتها في كوكب واحد منفرد يسمى المقبض. "
        "هذا الكوكب يصبح بوابة التعبير عن الخريطة كلها؛ من خلاله يتحرك الشخص، ومن خلال رمزيته يفرغ الضغط أو يوجه حياته. "
        "إذا نضج هذا الكوكب أصبح أداة قيادة وتركيز، وإذا لم ينضج قد يتحول إلى نقطة تعلق أو رد فعل زائد. "
        "مفتاح النمو هنا هو فهم الكوكب المقبض واستعماله بوعي بدل أن يقود الشخصية بصورة لا إرادية."
    ),
    "Splash": (
        "الشرح العملي للقارئ: نمط الرش يعني أن الكواكب منتشرة في أجزاء واسعة من الخريطة، ولذلك يكون الشخص متعدد الاهتمامات والتجارب. "
        "قد يملك قابلية للتعامل مع أكثر من مجال وأكثر من نوع من الناس، ولا يحب أن يُحصر في اتجاه واحد فقط. "
        "قوة هذا النمط في التنوع والمرونة والانفتاح، أما تحديه فهو التشتت أو صعوبة اختيار أولوية واحدة. "
        "مفتاح النمو هنا هو تحويل التعدد إلى شبكة خبرات منظمة لا إلى طاقة مبعثرة."
    ),
    "Seesaw": (
        "الشرح العملي للقارئ: نمط الأرجوحة يعني أن الحياة تُعاش غالبًا بين قطبين واضحين. "
        "الشخص يرى الأشياء من جهتين، ويشعر أحيانًا أنه مطالب بالموازنة بين اتجاهين متعارضين: الذات والآخر، البيت والعمل، العقل والعاطفة، الحرية والمسؤولية. "
        "قوة هذا النمط في القدرة على المقارنة ورؤية الجانبين، أما تحديه فهو التردد أو الشعور بالانقسام. "
        "مفتاح النمو هنا هو تحويل الشد الداخلي إلى مهارة في التوازن لا إلى صراع دائم."
    ),
    "Locomotive": (
        "الشرح العملي للقارئ: نمط القاطرة يعني أن هناك قوة دفع واضحة في الخريطة. "
        "الشخص يشعر غالبًا أنه يجب أن يتحرك أو يفتح الطريق أو يتقدم نحو هدف. "
        "الكوكب القائد هنا مهم جدًا لأنه يوضح كيف تبدأ الحركة: هل تبدأ بالفعل، بالكلام، بالمسؤولية، بالعاطفة، أو بالرؤية؟ "
        "قوة هذا النمط في الاندفاع والاستمرار، أما تحديه فهو التسرع أو الشعور الدائم بالضغط. "
        "مفتاح النمو هنا هو تحديد الوجهة قبل استخدام قوة الدفع."
    ),
    "Splay": (
        "الشرح العملي للقارئ: نمط التفرّع يعني أن الخريطة لا تتحرك من مركز واحد فقط، بل من عدة مراكز اهتمام. "
        "الشخص قد يكون مستقلًا وغير تقليدي، يجمع بين مجالات مختلفة أو يعيش مراحل متباينة في حياته. "
        "قوة هذا النمط في الأصالة وتعدد الموارد الداخلية، أما تحديه فهو صعوبة جمع هذه المسارات في هوية واحدة أو مشروع واضح. "
        "مفتاح النمو هنا هو بناء خيط ناظم يجمع الاهتمامات بدل تركها متفرقة."
    ),
    "Mixed_Seesaw_Splay": (
        "الشرح العملي للقارئ: هذا نمط مختلط بين التفرّع والأرجوحة. "
        "يوجد شد بين جهتين، لكن المجموعات ليست متوازنة بما يكفي لنقول إنها أرجوحة صافية. "
        "هذا يعني أن الشخص قد يشعر بتناقض أو سحب بين محورين، لكنه في الوقت نفسه يملك أكثر من مركز اهتمام وليس قطبين فقط. "
        "مفتاح النمو هنا هو عدم تبسيط الحياة إلى طرفين متصارعين، بل فهم المحاور المتعددة وتنظيمها."
    ),
    "Mixed_Locomotive_Splay": (
        "الشرح العملي للقارئ: هذا نمط مختلط بين القاطرة والتفرّع. "
        "هناك قوة دفع وفراغ واضح في الخريطة، لكن الكواكب ليست متصلة بما يكفي لتكون قاطرة صافية. "
        "هذا يعني أن الشخص يملك اندفاعًا نحو هدف، لكنه قد يتوزع في الوقت نفسه على أكثر من مسار. "
        "مفتاح النمو هنا هو اختيار مركز قيادة واضح ثم ترتيب بقية الاهتمامات حوله."
    ),
}


PLANET_HANDLE_REFLECTIONS = {
    "الشمس": (
        "لأن الشمس هي الكوكب المحوري هنا، فإن مفتاح الخريطة هو بناء الهوية والثقة والقدرة على الظهور. "
        "عندما يعرف الشخص من يكون وماذا يريد أن يترك من أثر، تتنظم بقية طاقته. "
        "التحدي هو ألا يربط قيمته كلها بالاعتراف أو الإعجاب."
    ),
    "القمر": (
        "لأن القمر هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو الأمان النفسي وإدارة المشاعر. "
        "الحياة تتحرك بقوة عندما يشعر الشخص بأنه محتوى ومطمئن. "
        "التحدي هو ألا تتحول الحاجة إلى الأمان إلى خوف أو تعلق أو تقلب مزاجي."
    ),
    "عطارد": (
        "لأن عطارد هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو التفكير والكلام والتعلم وربط المعلومات. "
        "الشخص يوجه حياته عبر الفهم، السؤال، التواصل، أو التحليل. "
        "التحدي هو ألا تتحول كثرة التفكير إلى تشتت أو قلق أو كلام غير محسوب."
    ),
    "الزهرة": (
        "لأن الزهرة هي الكوكب المحوري هنا، فإن مفتاح الخريطة هو العلاقات والقبول والذوق والقيمة والمال اللطيف. "
        "الشخص يفتح أبوابه غالبًا عبر الانسجام أو الجمال أو المحبة أو القدرة على جذب الناس. "
        "التحدي هو ألا تصبح قيمته معلقة بقبول الآخرين أو الخوف من الرفض."
    ),
    "المريخ": (
        "لأن المريخ هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو الفعل والمبادرة والدفاع وإدارة الغضب. "
        "الشخص لا يخرج من الضغط بالكلام فقط، بل يحتاج إلى حركة وقرار وفعل واضح. "
        "إذا نضج المريخ تحولت الحساسية أو التوتر إلى شجاعة وإنجاز، وإذا لم ينضج قد يظهر كاندفاع أو رد فعل دفاعي."
    ),
    "المشتري": (
        "لأن المشتري هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو الثقة والمعرفة والتوسع والفرص. "
        "الشخص يتحرك عندما يرى معنى أكبر أو أفقًا أوسع. "
        "التحدي هو ألا تتحول الثقة إلى مبالغة، أو الوعد إلى توسع بلا خطة."
    ),
    "زحل": (
        "لأن زحل هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو المسؤولية والصبر والبناء الطويل. "
        "الشخص يتحرك عندما يشعر أن عليه واجبًا أو هدفًا يستحق الالتزام. "
        "التحدي هو ألا يتحول الالتزام إلى ثقل دائم أو خوف من الفشل."
    ),
    "أورانوس": (
        "لأن أورانوس هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو التحرر والاختلاف والابتكار. "
        "الشخص يتحرك عندما يشعر أنه يستطيع كسر النمط أو فتح طريق جديد. "
        "التحدي هو ألا تتحول الحرية إلى قطيعة أو تمرد بلا اتجاه."
    ),
    "نبتون": (
        "لأن نبتون هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو الخيال والحدس والإلهام والروحانية. "
        "الشخص يتحرك من الصورة الداخلية أو الإحساس الخفي أكثر من المنطق المباشر. "
        "التحدي هو ألا يتحول الإلهام إلى ضبابية أو تعلق بصورة غير واقعية."
    ),
    "بلوتو": (
        "لأن بلوتو هو الكوكب المحوري هنا، فإن مفتاح الخريطة هو التحول العميق والقوة الداخلية وكشف الخفي. "
        "الشخص يتحرك بقوة في الأزمات وعند الحاجة لإعادة البناء. "
        "التحدي هو ألا تتحول القوة إلى سيطرة أو خوف من الفقد."
    ),
}


def pattern_life_reflection(pattern: str, leader_name: str = "") -> str:
    """
    شرح حياتي مباشر لنمط الخريطة، مع شرح الكوكب المقبض أو القائد إن وجد.
    """
    base = PATTERN_LIFE_REFLECTIONS.get(pattern, PATTERN_LIFE_REFLECTIONS["Splay"])
    if leader_name:
        handle_text = PLANET_HANDLE_REFLECTIONS.get(leader_name, "")
        if handle_text:
            return base + " " + handle_text
    return base



def sorted_planet_points(positions: Dict[str, BodyPosition]) -> List[Tuple[float, str, str]]:
    order = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
    pts = []
    for key in order:
        p = positions[key]
        pts.append((normalize_deg(p.lon), key, p.name_ar))
    pts.sort(key=lambda x: x[0])
    return pts


def circular_gaps(points: List[Tuple[float, str, str]]) -> List[Dict[str, object]]:
    gaps = []
    n = len(points)
    for i in range(n):
        current_lon, current_key, current_ar = points[i]
        next_lon, next_key, next_ar = points[(i + 1) % n]
        gap = normalize_deg(next_lon - current_lon)
        gaps.append({
            "gap": gap,
            "from": points[i],
            "to": points[(i + 1) % n],
            "index": i,
        })
    gaps.sort(key=lambda x: float(x["gap"]), reverse=True)
    return gaps


def minimal_arc_span(points: List[Tuple[float, str, str]]) -> Tuple[float, Dict[str, object]]:
    """
    أصغر قوس يحتوي كل الكواكب = 360 - أكبر فراغ.
    """
    gaps = circular_gaps(points)
    largest = gaps[0]
    span = 360.0 - float(largest["gap"])
    return span, largest


def arc_span_for_subset(subset: List[Tuple[float, str, str]]) -> float:
    """
    أصغر قوس يحتوي مجموعة كواكب معينة.
    """
    if len(subset) <= 1:
        return 0.0
    subset_sorted = sorted(subset, key=lambda x: x[0])
    gaps = circular_gaps(subset_sorted)
    largest = gaps[0]
    return 360.0 - float(largest["gap"])


def split_clusters(points: List[Tuple[float, str, str]], gap_threshold: float = 60.0) -> List[List[Tuple[float, str, str]]]:
    """
    تقسيم الكواكب إلى تجمعات حسب الفراغات الكبيرة.
    نبدأ من بعد أكبر فراغ حتى لا ينكسر التجمع عند 0°.
    """
    if not points:
        return []

    pts = sorted(points, key=lambda x: x[0])
    gaps_original = []
    n = len(pts)
    for i in range(n):
        gap = normalize_deg(pts[(i + 1) % n][0] - pts[i][0])
        gaps_original.append((gap, i))

    # البداية من بعد أكبر فراغ
    largest_gap_index = max(gaps_original, key=lambda x: x[0])[1]
    ordered = pts[largest_gap_index + 1:] + pts[:largest_gap_index + 1]

    clusters: List[List[Tuple[float, str, str]]] = [[ordered[0]]]
    for i in range(len(ordered) - 1):
        gap = normalize_deg(ordered[i + 1][0] - ordered[i][0])
        if gap >= gap_threshold:
            clusters.append([ordered[i + 1]])
        else:
            clusters[-1].append(ordered[i + 1])

    return clusters


def occupied_sign_count(points: List[Tuple[float, str, str]]) -> int:
    return len(set(int(p[0] // 30) for p in points))


def find_bucket_handle(points: List[Tuple[float, str, str]]) -> Optional[Tuple[float, str, str]]:
    """
    قاعدة مشددة للدلو Bucket:
    - 9 كواكب تقريبًا يجب أن تكون داخل كتلة واحدة واضحة.
    - الكوكب العاشر منفرد بوضوح عن طرفي الكتلة.
    - لا نقبل Bucket إذا كانت هناك كتلتان واضحتان أو أكثر.
    """
    candidates = []

    for candidate in points:
        others = [p for p in points if p != candidate]
        others_span = arc_span_for_subset(others)

        # التسعة الباقية يجب أن تكون ضمن نصف الخريطة تقريبًا.
        if others_span > 190:
            continue

        all_sorted = sorted(points, key=lambda x: x[0])
        idx = all_sorted.index(candidate)
        prev_pt = all_sorted[(idx - 1) % len(all_sorted)]
        next_pt = all_sorted[(idx + 1) % len(all_sorted)]

        left_gap = normalize_deg(candidate[0] - prev_pt[0])
        right_gap = normalize_deg(next_pt[0] - candidate[0])

        # المقبض الحقيقي يجب أن يكون واضح العزلة من الجهتين.
        if min(left_gap, right_gap) < 40:
            continue
        if left_gap + right_gap < 125:
            continue

        # نتأكد أن التسعة ليست مقسمة إلى أكثر من كتلة كبيرة.
        other_clusters = split_clusters(others, gap_threshold=60)
        if len([c for c in other_clusters if len(c) >= 2]) > 1:
            continue

        score = (190 - others_span) + (left_gap + right_gap)
        candidates.append((score, candidate))

    if candidates:
        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates[0][1]

    return None


def leading_planet_after_gap(largest_gap: Dict[str, object]) -> Tuple[float, str, str]:
    """
    الكوكب القائد في القاطرة هو أول كوكب بعد الفراغ الكبير.
    """
    return largest_gap["to"]  # type: ignore


def classify_chart_pattern(positions: Dict[str, BodyPosition]) -> Dict[str, object]:
    """
    تصنيف شامل لأنماط الخرائط:
    Bundle, Bowl, Bucket, Splash, Seesaw, Locomotive, Splay.

    الفكرة:
    - Bundle: كل الكواكب داخل 120° أو أقل.
    - Bowl: كل الكواكب داخل نصف الخريطة تقريبًا، بدون مقبض منفرد.
    - Bucket: 9 كواكب في كتلة + كوكب منفرد حقيقي.
    - Splash: انتشار واسع بلا فجوات كبيرة.
    - Seesaw: مجموعتان واضحتان يفصل بينهما فراغان كبيران، وكل مجموعة فيها كوكبان أو أكثر.
    - Locomotive: انتشار على نحو 240° مع فراغ كبير واحد، بدون انقسام إلى مجموعتين واضحتين.
    - Splay: ثلاث تجمعات أو توزيع غير منتظم لا ينطبق عليه ما سبق.
    """
    points = sorted_planet_points(positions)
    gaps = circular_gaps(points)
    span, largest_gap = minimal_arc_span(points)
    largest_gap_value = float(largest_gap["gap"])
    second_gap_value = float(gaps[1]["gap"]) if len(gaps) > 1 else 0.0
    signs_count = occupied_sign_count(points)

    clusters_60 = split_clusters(points, gap_threshold=60)
    clusters_50 = split_clusters(points, gap_threshold=50)
    strong_clusters = [c for c in clusters_60 if len(c) >= 2]

    cluster_sizes = sorted([len(c) for c in strong_clusters], reverse=True)
    seesaw_balanced = False
    if len(cluster_sizes) == 2:
        smaller = min(cluster_sizes)
        larger = max(cluster_sizes)
        # الأرجوحة الصافية تحتاج مجموعتين معتبرتين ومتقاربتين نسبيًا.
        # 2 مقابل 8 ليست أرجوحة صافية.
        seesaw_balanced = smaller >= 3 and (larger / smaller) <= 2.25

    handle = find_bucket_handle(points)
    pattern = "Splay"
    leader = None
    confidence = "متوسط"

    # 1) الحزمة: تركيز شديد.
    if span <= 120:
        pattern = "Bundle"
        confidence = "عالٍ"

    # 2) الدلو: لا يُقبل إلا بمقبض حقيقي.
    elif handle is not None:
        pattern = "Bucket"
        leader = handle
        confidence = "عالٍ"

    # 3) الوعاء: كل الكواكب في نصف الخريطة تقريبًا.
    elif span <= 195:
        pattern = "Bowl"
        confidence = "عالٍ" if span <= 185 else "متوسط"

    # 4) الرش: انتشار واسع بلا فجوة كبرى وبعدد أبراج واسع.
    elif largest_gap_value < 70 and signs_count >= 7:
        pattern = "Splash"
        confidence = "عالٍ"

    # 5) الأرجوحة الصافية: مجموعتان واضحتان ومتقاربتان نسبيًا.
    elif len(strong_clusters) == 2 and seesaw_balanced and largest_gap_value >= 70 and second_gap_value >= 55:
        pattern = "Seesaw"
        confidence = "عالٍ" if second_gap_value >= 70 else "متوسط"

    # 5b) مجموعتان واضحتان لكن غير متوازنتين: تفرع مع ميل إلى الأرجوحة.
    elif len(strong_clusters) == 2 and not seesaw_balanced and largest_gap_value >= 70 and second_gap_value >= 55:
        pattern = "Mixed_Seesaw_Splay"
        confidence = "متوسط"

    # 6) القاطرة الصافية: فراغ كبير واحد وانتشار على ثلثي الخريطة تقريبًا، مع عدم وجود فراغ ثانٍ كبير.
    elif 205 <= span <= 285 and 75 <= largest_gap_value <= 155 and second_gap_value < 70:
        pattern = "Locomotive"
        leader = leading_planet_after_gap(largest_gap)
        confidence = "متوسط" if largest_gap_value < 90 or largest_gap_value > 140 else "عالٍ"

    # 6b) قاطرة غير صافية بسبب فراغ ثانٍ كبير: تفرع مع ميل إلى القاطرة.
    elif 205 <= span <= 285 and 75 <= largest_gap_value <= 155 and 70 <= second_gap_value < 90:
        pattern = "Mixed_Locomotive_Splay"
        leader = leading_planet_after_gap(largest_gap)
        confidence = "متوسط"

    # 7) إذا كانت هناك ثلاث كتل أو أكثر فهو تفرّع.
    elif len([c for c in clusters_50 if len(c) >= 2]) >= 3:
        pattern = "Splay"
        confidence = "عالٍ"

    # 8) الحالات المختلطة.
    else:
        pattern = "Splay"
        confidence = "متوسط"

    return {
        "points": points,
        "gaps": gaps,
        "span": span,
        "largest_gap": largest_gap,
        "largest_gap_value": largest_gap_value,
        "second_gap_value": second_gap_value,
        "clusters_60": clusters_60,
        "clusters_50": clusters_50,
        "strong_clusters": strong_clusters,
        "signs_count": signs_count,
        "handle": handle,
        "pattern": pattern,
        "leader": leader,
        "confidence": confidence,
    }

def pattern_reason(pattern: str, data: Dict[str, object]) -> str:
    span = float(data["span"])
    largest_gap_value = float(data["largest_gap_value"])
    second_gap_value = float(data["second_gap_value"])
    signs_count = int(data["signs_count"])
    strong_clusters = data["strong_clusters"]
    handle = data["handle"]

    if pattern == "Bundle":
        return f"لأن الكواكب كلها تقريبًا محصورة داخل قوس صغير قدره نحو {span:.0f} درجة، وهذا يدل على تركيز شديد للطاقة."
    if pattern == "Bowl":
        return f"لأن الكواكب تقع تقريبًا داخل نصف الخريطة أو قريبًا منه، مع فراغ كبير يقارب {largest_gap_value:.0f} درجة، ولا يوجد كوكب منفرد حقيقي يصلح كمقبض."
    if pattern == "Bucket" and handle:
        return f"لأن تسعة كواكب تقريبًا تتجمع في كتلة واحدة واضحة، مع كوكب منفرد هو {handle[2]} يعمل كمقبض حقيقي للخريطة."
    if pattern == "Splash":
        return f"لأن الكواكب منتشرة في أغلب أجزاء الخريطة، وتشغل نحو {signs_count} أبراج، ولا توجد فجوة كبرى تسيطر على التوزيع."
    if pattern == "Seesaw":
        sizes = sorted([len(c) for c in strong_clusters], reverse=True)  # type: ignore
        return f"لأن الكواكب منقسمة إلى مجموعتين واضحتين ومتقاربتين نسبيًا؛ المجموعة الأكبر تضم نحو {sizes[0]} كواكب، والأصغر تضم نحو {sizes[1]} كواكب، ويفصل بينهما فراغان كبيران."
    if pattern == "Mixed_Seesaw_Splay":
        sizes = sorted([len(c) for c in strong_clusters], reverse=True)  # type: ignore
        return f"لأن هناك مجموعتين واضحتين لكن غير متوازنتين؛ المجموعة الأكبر تضم نحو {sizes[0]} كواكب، والأصغر نحو {sizes[1]} كواكب، مع فراغين كبيرين. لذلك لا نعدّها أرجوحة صافية."
    if pattern == "Locomotive":
        return f"لأن الكواكب تنتشر على قوس واسع يقارب {span:.0f} درجة، مع فراغ كبير واحد يقارب {largest_gap_value:.0f} درجة، ولا توجد كتلتان متقابلتان واضحتان."
    if pattern == "Mixed_Locomotive_Splay":
        return f"لأن هناك فراغًا كبيرًا يعطي دفع القاطرة، لكن وجود فراغ ثانٍ معتبر يجعل التوزيع غير متصل تمامًا، لذلك لا نعدّها قاطرة صافية."
    return "لأن توزيع الكواكب غير منتظم أو مقسّم إلى عدة مراكز اهتمام، ولا تنطبق عليه شروط الحزمة أو الوعاء أو الدلو أو الرش أو الأرجوحة أو القاطرة بدقة."

def detect_chart_pattern(positions: Dict[str, BodyPosition]) -> Dict[str, object]:
    data = classify_chart_pattern(positions)

    pattern = str(data["pattern"])
    leader = data["leader"]
    ar_name = PATTERN_AR_NAMES.get(pattern, pattern)
    meaning = PATTERN_MEANINGS.get(pattern, PATTERN_MEANINGS["Splay"])

    reason = pattern_reason(pattern, data)
    leader_text = ""
    leader_name = ""
    if leader is not None:
        leader_name = leader[2]
        leader_text = (
            f"الكوكب القائد أو المحوري في هذا النمط هو {leader_name}. "
            + PLANET_LEADER_MEANINGS.get(leader_name, "")
        )

    confidence = data.get("confidence", "متوسط")
    life_reflection = pattern_life_reflection(pattern, leader_name)

    text = (
        f"نوع الخريطة: {ar_name} ({pattern}). "
        f"درجة الثقة في التصنيف: {confidence}. "
        f"{reason} "
        f"{meaning['meaning']} {meaning['strength']} {meaning['challenge']} "
        f"{leader_text} "
        f"{life_reflection} "
        f"{meaning['advice']}"
    )

    return {
        "pattern": pattern,
        "ar_name": ar_name,
        "span": round(float(data["span"]), 2),
        "largest_gap": round(float(data["largest_gap_value"]), 2),
        "second_gap": round(float(data["second_gap_value"]), 2),
        "clusters": len(data["clusters_60"]),  # type: ignore
        "occupied_signs": int(data["signs_count"]),
        "leader": leader[2] if leader is not None else "",
        "confidence": confidence,
        "text": text,
    }





# ============================================================
# تحليل الاتصالات الرئيسية
# ============================================================

ASPECT_NATURE = {
    "اقتران": "مركّز",
    "تربيع": "ضاغط",
    "مقابلة": "ضاغط",
    "تثليث": "داعم",
    "تسديس": "داعم",
}

ASPECT_BASE_MEANING = {
    "اقتران": "الاقتران يعني أن طاقتين تعملان في نقطة واحدة، لذلك يكون أثره قويًا ومركّزًا وقد يظهر كصفة واضحة في الشخصية.",
    "تربيع": "التربيع يدل على احتكاك داخلي أو ضغط يدفع إلى النمو. ليس سلبيًا بالضرورة، لكنه يحتاج إلى وعي حتى لا يتحول إلى توتر أو رد فعل.",
    "مقابلة": "المقابلة تدل على شدّ بين طرفين أو حاجتين متقابلتين. قوتها في الوعي بالآخر والتوازن، وتحديها في عدم العيش بين نقيضين دائمًا.",
    "تثليث": "التثليث يدل على موهبة أو انسجام طبيعي بين طاقتين. قوته أنه يسهل التعبير، وتحديه أن لا يبقى كسلًا أو طاقة غير مستثمرة.",
    "تسديس": "التسديس يدل على فرصة قابلة للتفعيل. لا يعمل دائمًا وحده، لكنه يعطي منفذًا جيدًا إذا بادر الشخص إلى استخدامه."
}

PLANET_PAIR_MEANINGS = {
    ("الشمس", "القمر"): "هذا الاتصال يربط الإرادة بالمشاعر، ويؤثر في التوازن بين ما يريده الشخص وما يحتاجه نفسيًا.",
    ("الشمس", "عطارد"): "هذا الاتصال يربط الهوية بالتفكير والكلام، وقد يعطي حضورًا ذهنيًا أو حاجة للتعبير عن الرأي.",
    ("الشمس", "الزهرة"): "هذا الاتصال يربط الهوية بالقبول والجمال والعاطفة، ويدعم الذوق والجاذبية والرغبة في الانسجام.",
    ("الشمس", "المريخ"): "هذا الاتصال يربط الإرادة بالفعل، ويزيد الشجاعة والمبادرة، لكنه يحتاج إلى تهذيب الاندفاع.",
    ("الشمس", "المشتري"): "هذا الاتصال يربط الهوية بالتوسع والثقة، وقد يعطي طموحًا ورغبة في النمو أو الظهور.",
    ("الشمس", "زحل"): "هذا الاتصال يعطي جدية ومسؤولية وإحساسًا مبكرًا بضرورة إثبات الذات. قوته في الصبر، وتحديه في القسوة على النفس.",
    ("الشمس", "أورانوس"): "هذا الاتصال يعطي استقلالًا ورغبة في الاختلاف وكسر النمط. قوته في الابتكار، وتحديه في التمرد أو عدم الثبات.",
    ("الشمس", "نبتون"): "هذا الاتصال يربط الهوية بالخيال والحدس، وقد يعطي إلهامًا وحسًا روحيًا، لكنه يحتاج إلى وضوح حتى لا يسبب ضبابية.",
    ("الشمس", "بلوتو"): "هذا الاتصال عميق وقوي، يدل على إرادة تحول وتجارب تعيد بناء الذات. قوته في العمق، وتحديه في السيطرة أو صراعات القوة.",

    ("القمر", "عطارد"): "هذا الاتصال يربط المشاعر بالتفكير والكلام، وقد يعطي قدرة على التعبير عن الإحساس أو تحليل المزاج.",
    ("القمر", "الزهرة"): "هذا الاتصال يدعم اللطف والقبول والحاجة إلى الحنان والانسجام العاطفي.",
    ("القمر", "المريخ"): "هذا الاتصال يزيد سرعة الانفعال ورد الفعل. قوته في الحماس والحماية، وتحديه في الغضب أو التسرع.",
    ("القمر", "المشتري"): "هذا الاتصال يعطي اتساعًا عاطفيًا وتعاطفًا وثقة، وقد يدعم الحماية والكرم النفسي.",
    ("القمر", "زحل"): "هذا الاتصال يعطي تحفظًا عاطفيًا أو شعورًا بالمسؤولية النفسية. قوته في النضج، وتحديه في الكتمان أو البرود الظاهري.",
    ("القمر", "أورانوس"): "هذا الاتصال يجعل المزاج سريع التغير أو مستقلًا. قوته في التحرر من الأنماط، وتحديه في التوتر وعدم الاستقرار.",
    ("القمر", "نبتون"): "هذا الاتصال يعطي حساسية وحدسًا وخيالًا، لكنه يحتاج إلى حدود نفسية واضحة حتى لا يسبب ذوبانًا أو مثالية.",
    ("القمر", "بلوتو"): "هذا الاتصال عميق نفسيًا، وقد يدل على مشاعر قوية وتجارب تحول. قوته في الشفاء، وتحديه في التعلق أو الخوف العميق.",

    ("عطارد", "الزهرة"): "هذا الاتصال يعطي لطفًا في الكلام وذوقًا في التعبير، ويفيد في الكتابة، الإقناع، الفن، أو التعليم اللطيف.",
    ("عطارد", "المريخ"): "هذا الاتصال يسرّع التفكير والكلام. قوته في الحسم، وتحديه في حدّة اللسان أو التسرع في الرد.",
    ("عطارد", "المشتري"): "هذا الاتصال يوسع التفكير ويدعم التعلم والسفر واللغات، لكنه يحتاج إلى عدم المبالغة أو التشتت.",
    ("عطارد", "زحل"): "هذا الاتصال يعطي عقلًا جادًا ومنهجيًا، وقد يفيد في البحث والتنظيم، لكنه قد يزيد القلق أو التردد في الكلام.",
    ("عطارد", "أورانوس"): "هذا الاتصال يعطي ذكاءً مفاجئًا وأفكارًا مختلفة، ويفيد في التقنية والابتكار والتحليل السريع.",
    ("عطارد", "نبتون"): "هذا الاتصال يعطي خيالًا وحدسًا في التفكير، لكنه يحتاج إلى تدقيق حتى لا تختلط الفكرة بالوهم أو سوء الفهم.",
    ("عطارد", "بلوتو"): "هذا الاتصال يعطي عمقًا فكريًا وقدرة على كشف الخفي، لكنه يحتاج إلى تجنب الهوس أو الشك الزائد.",

    ("الزهرة", "المريخ"): "هذا الاتصال يزيد الجاذبية والحركة العاطفية، ويربط الحب بالرغبة والفعل. يحتاج إلى تهذيب الانفعال داخل العلاقات.",
    ("الزهرة", "المشتري"): "هذا الاتصال يدعم القبول والكرم والفرص الاجتماعية أو المالية، لكنه يحتاج إلى ضبط المبالغة أو التوقعات العالية.",
    ("الزهرة", "زحل"): "هذا الاتصال يعطي جدية في الحب والمال، وقد يشير إلى تأخر أو تحفظ، لكنه يدعم العلاقات الناضجة إذا وُجد الصبر.",
    ("الزهرة", "أورانوس"): "هذا الاتصال يعطي ذوقًا مختلفًا وحاجة إلى حرية في العلاقات، لكنه قد يسبب مفاجآت أو عدم ثبات عاطفي.",
    ("الزهرة", "نبتون"): "هذا الاتصال يعطي رومانسية وخيالًا وفنًا، لكنه يحتاج إلى وضوح حتى لا تتحول المثالية إلى خيبة.",
    ("الزهرة", "بلوتو"): "هذا الاتصال يعطي عمقًا وجاذبية قوية في العلاقات، لكنه يحتاج إلى تجنب السيطرة أو التعلق الشديد.",

    ("المريخ", "المشتري"): "هذا الاتصال يزيد الجرأة والحماس والطاقة، وقد يدعم الإنجاز، لكنه يحتاج إلى خطة حتى لا يتحول إلى تهور.",
    ("المريخ", "زحل"): "هذا الاتصال يضع الفعل أمام الحدود. قوته في الصبر والعمل الشاق، وتحديه في الإحباط أو الغضب المكبوت.",
    ("المريخ", "أورانوس"): "هذا الاتصال يعطي اندفاعًا للتحرر وسرعة في الفعل، لكنه يحتاج إلى تجنب القرارات المفاجئة.",
    ("المريخ", "نبتون"): "هذا الاتصال يخلط الفعل بالخيال أو الحساسية، وقد يعطي إلهامًا في العمل، لكنه يحتاج إلى وضوح في الهدف.",
    ("المريخ", "بلوتو"): "هذا الاتصال قوي جدًا في الإرادة والتحول، وقد يعطي قدرة على المواجهة، لكنه يحتاج إلى ضبط القوة والسيطرة.",

    ("المشتري", "زحل"): "هذا الاتصال يوازن بين التوسع والحدود. قوته في بناء فرصة واقعية، وتحديه في الشد بين التفاؤل والخوف.",
    ("المشتري", "أورانوس"): "هذا الاتصال يعطي فرصًا مفاجئة ورغبة في التوسع والحرية، لكنه يحتاج إلى عدم التسرع.",
    ("المشتري", "نبتون"): "هذا الاتصال يعطي مثالية وإيمانًا وخيالًا واسعًا، لكنه يحتاج إلى تمييز بين الرؤية والحلم غير الواقعي.",
    ("المشتري", "بلوتو"): "هذا الاتصال يعطي طموحًا وقوة توسع وتأثير، لكنه يحتاج إلى أخلاق واضحة في استخدام النفوذ.",

    ("زحل", "أورانوس"): "هذا الاتصال يربط القديم بالجديد، وقد يخلق شدًا بين النظام والحرية. قوته في تحديث البنية دون هدمها.",
    ("زحل", "نبتون"): "هذا الاتصال يربط الحلم بالواقع، وقد يعطي قدرة على تجسيد الرؤية، لكنه يحتاج إلى عدم الاستسلام للغموض أو الإحباط.",
    ("زحل", "بلوتو"): "هذا الاتصال عميق وثقيل، يدل على اختبارات في القوة والصبر. قوته في إعادة البناء، وتحديه في الخوف أو التشدد.",

    ("أورانوس", "نبتون"): "هذا الاتصال جيلي غالبًا، ويدل على خيال مستقبلي وتغيير في الرؤية أو الوعي.",
    ("أورانوس", "بلوتو"): "هذا الاتصال جيلي غالبًا، ويدل على تغيير جذري ورغبة في التحرر والتحول.",
    ("نبتون", "بلوتو"): "هذا الاتصال جيلي غالبًا، ويدل على تحولات عميقة في الحس الروحي واللاوعي الجمعي."
}


def pair_key(a: str, b: str) -> Tuple[str, str]:
    """
    توحيد ترتيب أزواج الكواكب حسب ترتيب تقريبي من الأسرع/الشخصي إلى الأثقل.
    """
    order = {
        "الشمس": 1, "القمر": 2, "عطارد": 3, "الزهرة": 4, "المريخ": 5,
        "المشتري": 6, "زحل": 7, "أورانوس": 8, "نبتون": 9, "بلوتو": 10
    }
    return (a, b) if order.get(a, 99) <= order.get(b, 99) else (b, a)


def aspect_priority_score(a: str, b: str, asp: str, orb: float) -> float:
    """
    ترتيب الاتصالات المهمة: الأورب الأقل، والاتصالات الضاغطة/الاقتران، والكواكب الشخصية.
    """
    score = max(0.0, 10.0 - float(orb))

    if asp in ["اقتران", "تربيع", "مقابلة"]:
        score += 4
    elif asp in ["تثليث", "تسديس"]:
        score += 2

    personal = {"الشمس", "القمر", "عطارد", "الزهرة", "المريخ"}
    if a in personal:
        score += 2
    if b in personal:
        score += 2

    angles_like = {"الشمس", "القمر"}
    if a in angles_like or b in angles_like:
        score += 1.5

    return score


def aspect_reading_text(a: str, b: str, asp: str, orb: float) -> str:
    nature = ASPECT_NATURE.get(asp, "مؤثر")
    base = ASPECT_BASE_MEANING.get(asp, "")
    meaning = PLANET_PAIR_MEANINGS.get(pair_key(a, b), "هذا الاتصال يربط دلالتين مهمتين في الخريطة، ويُقرأ حسب طبيعة الكوكبين والبيت الذي يقع فيه كل منهما.")

    if nature == "ضاغط":
        advice = "النصيحة: لا تتعامل مع هذا الاتصال كعائق، بل كطاقة تحتاج إلى وعي وتنظيم حتى تتحول إلى نضج."
    elif nature == "داعم":
        advice = "النصيحة: هذه موهبة أو فرصة، لكنها تحتاج إلى استخدام عملي حتى لا تبقى كامنة."
    else:
        advice = "النصيحة: لأن هذا الاتصال مركّز، فمن المهم توجيهه بوعي حتى لا يطغى على بقية الشخصية."

    return (
        f"{a} {asp} {b} بفارق {orb:.2f}°. "
        f"نوع الاتصال: {nature}. {base} {meaning} {advice}"
    )


def generate_aspects_analysis(aspects) -> List[str]:
    """
    تحليل مختصر لأهم الاتصالات في الخريطة.
    لا نحلل كل الاتصالات حتى لا يطول التقرير، بل نختار الأهم.
    """
    if not aspects:
        return ["لا توجد اتصالات رئيسية واضحة ضمن الأورب المعتمد في هذه النسخة."]

    rows = []
    for a, b, asp, orb in aspects:
        rows.append((aspect_priority_score(a, b, asp, float(orb)), a, b, asp, float(orb)))

    rows.sort(key=lambda x: x[0], reverse=True)

    # نختار أهم 8 اتصالات كحد أعلى
    selected = rows[:8]
    return [aspect_reading_text(a, b, asp, orb) for score, a, b, asp, orb in selected]



# ============================================================
# جداول مواقع الكواكب والكويكبات والنقاط المهمة
# ============================================================

# كويكبات ونقاط إضافية مهمة للباحث الفلكي.
# بعضها حقيقي في Swiss Ephemeris، وبعض النقاط تُحسب عند توفرها.
ADDITIONAL_POINTS = [
    ("Chiron", "كايرون", "swe.CHIRON", True),
    ("Lilith", "ليليث", "swe.MEAN_APOG", False),
    ("NorthNode", "الرأس الشمالي", "swe.MEAN_NODE", False),
    ("SouthNode", "الذنب الجنوبي", "CALCULATED_SOUTH_NODE", False),
    ("Ceres", "سيريس", "swe.CERES", True),
    ("Pallas", "بالاس", "swe.PALLAS", True),
    ("Juno", "جونو", "swe.JUNO", True),
    ("Vesta", "فيستا", "swe.VESTA", True),
    ("Pholus", "فولو", "swe.PHOLUS", True),
]



IMPORTANT_POINT_MEANINGS = {
    "كايرون": {
        "core": "كايرون يمثل الجرح العميق الذي يتحول مع الوعي إلى حكمة وقدرة على الشفاء ومساعدة الآخرين.",
        "growth": "في قراءة النمو الذاتي، كايرون لا يُقرأ كضعف فقط، بل كمنطقة حساسة تحتاج إلى قبول ووعي حتى تتحول إلى موهبة علاجية أو فهم إنساني عميق."
    },
    "الرأس الشمالي": {
        "core": "العقدة الشمالية تمثل اتجاه النمو والتطور، أي الطريق الذي يدفع الشخص إلى الخروج من المألوف واكتساب خبرة جديدة.",
        "growth": "هي ليست سهلة دائمًا، لأنها تطلب من الشخص أن يتعلم سلوكًا جديدًا ويتقدم نحو منطقة غير معتادة في حياته."
    },
    "الذنب الجنوبي": {
        "core": "العقدة الجنوبية تمثل الخبرة القديمة أو النمط المألوف الذي يحمله الشخص بسهولة، لكنه قد يصبح منطقة تكرار أو ركود إذا بقي متعلقًا بها.",
        "growth": "المطلوب هنا ليس رفض الماضي، بل استخدامه كخبرة دون البقاء أسيرًا له."
    },
    "جونو": {
        "core": "جونو تمثل نمط الالتزام والشراكة والاحتياج إلى العدل داخل العلاقات العميقة أو الزواج.",
        "growth": "توضح ما الذي يحتاجه الشخص حتى يشعر أن العلاقة متوازنة ومحترمة، وما الذي قد يثير لديه حساسية تجاه الإهمال أو عدم الإنصاف."
    },
    "فيستا": {
        "core": "فيستا تمثل التركيز الداخلي، الإخلاص، الخدمة، والطاقة التي تحتاج إلى عزلة أو انضباط كي تبقى نقية ومثمرة.",
        "growth": "توضح أين يستطيع الشخص أن يكرّس نفسه بعمق، وأين يحتاج إلى حماية طاقته من الاستنزاف."
    },
    "بالاس": {
        "core": "بالاس تمثل الذكاء الاستراتيجي، حل المشكلات، قراءة الأنماط، والحكمة العملية في اتخاذ القرار.",
        "growth": "توضح الطريقة التي يفكر بها الشخص عندما يريد أن يحلل أو يخطط أو يجد حلًا ذكيًا بعيدًا عن الانفعال."
    },
    "فولو": {
        "core": "فولوس يمثل الشرارة الصغيرة التي قد تطلق سلسلة من الأحداث أو التحولات الكبيرة، لذلك يرتبط بردود الفعل المتسلسلة والنتائج غير المتوقعة.",
        "growth": "يوضح أين يجب الانتباه من قرارات بسيطة قد تفتح بابًا واسعًا، كما يوضح أين يمكن لخطوة صغيرة واعية أن تغيّر مسارًا كاملًا."
    },
    "سيريس": {
        "core": "سيريس تمثل الرعاية، التغذية، الاحتواء، العلاقة بالجسد والطعام، وطريقة العطاء أو استقبال العناية.",
        "growth": "توضح كيف يهتم الشخص بنفسه وبغيره، وأين يحتاج إلى توازن بين الرعاية وعدم استنزاف الذات."
    },
    "ليليث": {
        "core": "ليليث تمثل المنطقة البرية أو المكبوتة في النفس، وما قد يرفض الشخص الخضوع فيه أو يشعر أنه لا يريد التنازل عنه.",
        "growth": "توضح أين توجد قوة خام تحتاج إلى وعي، حتى لا تتحول إلى تمرد أو غضب صامت أو شعور بالرفض."
    },
}


def important_point_sign_house_text(name: str, sign: str, house: int, term: str, retro: str) -> str:
    sign_trait = SIGN_SIMPLE_TRAITS.get(sign, "")
    house_meaning = HOUSE_MEANINGS.get(house, "")
    meaning = IMPORTANT_POINT_MEANINGS.get(name, {
        "core": "هذه نقطة مساعدة في قراءة الخريطة وتحتاج إلى ربطها بالبرج والبيت والاتصالات.",
        "growth": "تُقرأ بوصفها مؤشرًا إضافيًا لا يحل محل الكواكب الأساسية."
    })

    motion_note = ""
    if retro == "متراجع":
        motion_note = " وكونها متراجعة يجعل معناها أكثر داخلية أو مرتبطًا بالمراجعة والتأمل قبل التعبير الخارجي."

    return (
        f"{name}: تقع في {sign} في البيت {house} ضمن حد {term}. "
        f"{meaning['core']} وجودها في {sign} يعطيها نبرة: {sign_trait} "
        f"أما وجودها في البيت {house} فيربطها بموضوع: {house_meaning} "
        f"والحد يضيف طبقة مهمة؛ {TERM_INTERPRETATION.get(term, '')}{motion_note} "
        f"{meaning['growth']}"
    )


def generate_asteroids_points_analysis(rows: List[Dict[str, object]]) -> List[str]:
    """
    تحليل مختصر للكويكبات والنقاط المهمة بعد حساب مواقعها.
    """
    if not rows:
        return ["لم تظهر الكويكبات أو النقاط المهمة في هذه النسخة من الحساب، وقد يكون السبب أن مكتبة Swiss Ephemeris على الجهاز لا تدعم بعضها."]

    priority = {
        "كايرون": 1,
        "الرأس الشمالي": 2,
        "الذنب الجنوبي": 3,
        "جونو": 4,
        "فيستا": 5,
        "بالاس": 6,
        "فولو": 7,
        "سيريس": 8,
        "ليليث": 9,
    }

    sorted_rows = sorted(rows, key=lambda r: priority.get(str(r.get("name", "")), 99))
    output = []
    unavailable = []

    for r in sorted_rows:
        try:
            if not bool(r.get("available", True)):
                unavailable.append(str(r.get("name", "")))
                continue

            output.append(
                important_point_sign_house_text(
                    str(r["name"]),
                    str(r["sign"]),
                    int(r["house"]),
                    str(r["term"]),
                    str(r["retro"]),
                )
            )
        except Exception:
            continue

    if unavailable:
        output.append(
            "ملاحظة فنية: حاول التطبيق حساب جميع الكويكبات المهمة، وحاول تحميل ملف الكويكبات تلقائيًا عند الحاجة. "
            "لكن بعض النقاط لم تُحسب في هذه البيئة، وهي: "
            + "، ".join([x for x in unavailable if x])
            + ". الحل العملي: تأكد من وجود اتصال إنترنت عند أول تشغيل، أو ضع ملف seas_18.se1 داخل مجلد sweph بجانب ملف التطبيق أو داخل Download/sweph."
        )

    return output

def dignity_status_for_table(key: str, sign: str) -> str:
    """
    حالة دستورية مختصرة للجدول.
    """
    if key not in PLANET_CONSTITUTION:
        return "-"
    return str(planet_sign_dignity(key, sign).get("status", "-"))


def format_lon_table(lon: float) -> Dict[str, object]:
    sign, degree = sign_from_lon(lon)
    return {
        "sign": sign,
        "degree": format_degree(degree),
        "term": get_ptolemy_term(sign, degree),
    }


def planet_positions_table(positions: Dict[str, BodyPosition]) -> List[Dict[str, object]]:
    """
    جدول الكواكب الأساسية.
    """
    order = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Uranus", "Neptune", "Pluto"]
    rows = []
    for key in order:
        p = positions[key]
        rows.append({
            "name": p.name_ar,
            "sign": p.sign,
            "degree": format_degree(p.degree),
            "house": p.house,
            "term": p.term,
            "retro": "متراجع" if p.retrograde else "مباشر",
            "dignity": dignity_status_for_table(key, p.sign),
        })
    return rows


def calculate_additional_points(jd_ut: float, cusps: List[float]) -> List[Dict[str, object]]:
    """
    حساب الكويكبات والنقاط المهمة.
    إذا لم يكن ملف الكويكبات موجودًا، يحاول التطبيق تحميله تلقائيًا ثم يعيد الحساب.
    """
    rows = []

    asteroid_file_ready = ensure_asteroid_ephemeris_ready()

    for item in ADDITIONAL_POINTS:
        # دعم الصيغة القديمة والجديدة احتياطًا
        if len(item) == 4:
            key, ar_name, swe_ref, needs_asteroid_file = item
        else:
            key, ar_name, swe_ref = item
            needs_asteroid_file = False

        try:
            if swe_ref == "CALCULATED_SOUTH_NODE":
                node_obj = getattr(swe, "MEAN_NODE", None)
                if node_obj is None:
                    raise RuntimeError("MEAN_NODE غير مدعوم")
                result = swe.calc_ut(jd_ut, node_obj, swe.FLG_SWIEPH | swe.FLG_SPEED)
                lon = normalize_deg(float(result[0][0]) + 180)
                speed = float(result[0][3]) if len(result[0]) > 3 else -1.0
                retro = speed < 0
            else:
                attr_name = swe_ref.split(".")[-1]
                obj = getattr(swe, attr_name, None)
                if obj is None:
                    raise RuntimeError(f"{attr_name} غير مدعوم في pyswisseph")

                # نحاول الحساب بعد ضبط المسار
                setup_swiss_ephemeris_path()
                result = swe.calc_ut(jd_ut, obj, swe.FLG_SWIEPH | swe.FLG_SPEED)
                lon = normalize_deg(float(result[0][0]))
                speed = float(result[0][3]) if len(result[0]) > 3 else 0.0
                retro = speed < 0

            loc = format_lon_table(lon)
            house = house_from_cusps(lon, cusps)
            rows.append({
                "name": ar_name,
                "sign": loc["sign"],
                "degree": loc["degree"],
                "house": house,
                "term": loc["term"],
                "retro": "متراجع" if retro else "مباشر",
                "available": True,
                "note": "",
            })

        except Exception as e:
            # بدل أن يختفي الكويكب، نظهره مع سبب مختصر
            if needs_asteroid_file:
                if asteroid_file_ready:
                    note = "تعذر حسابه رغم وجود ملف الكويكبات"
                else:
                    note = "تعذر تحميل ملف الكويكبات تلقائيًا؛ يحتاج اتصال إنترنت أو وضع seas_18.se1 داخل مجلد sweph"
            else:
                note = "غير محسوب في هذه البيئة"

            rows.append({
                "name": ar_name,
                "sign": "—",
                "degree": "—",
                "house": "—",
                "term": "—",
                "retro": note,
                "available": False,
                "note": str(e),
            })

    return rows



def generate_welcome_message(name: str, gender: str, positions, angles) -> Dict[str, str]:
    """
    بطاقة ترحيب قصيرة في بداية التقرير.
    """
    sun_sign = positions["Sun"].sign
    moon_sign = positions["Moon"].sign
    asc_sign, _ = sign_from_lon(angles["ASC"])

    sun_trait = SIGN_SIMPLE_TRAITS.get(sun_sign, "")
    moon_trait = SIGN_SIMPLE_TRAITS.get(moon_sign, "")
    asc_trait = SIGN_SIMPLE_TRAITS.get(asc_sign, "")

    name_clean = name.strip() if name else "صاحب الخريطة"

    line1 = f"أهلًا {name_clean}"
    line2 = f"شمسك في {sun_sign}، قمرك في {moon_sign}، وطالعك {asc_sign}."

    if gender == "أنثى":
        line3 = (
            "هذه الثلاثية هي مفتاح القراءة الأول: الشمس توضّح هويتكِ وإرادتكِ، "
            "والقمر يصف عالمكِ الداخلي واحتياجكِ النفسي، والطالع يبيّن طريقتكِ في الظهور والتعامل مع الحياة."
        )
        line4 = (
            f"بصورة مختصرة، يجمع هذا المزيج بين {sun_trait} "
            f"وبين نفس داخلية تحمل نبرة {moon_trait} "
            f"وطريقة ظهور تميل إلى {asc_trait}"
        )
    else:
        line3 = (
            "هذه الثلاثية هي مفتاح القراءة الأول: الشمس توضّح هويتك وإرادتك، "
            "والقمر يصف عالمك الداخلي واحتياجك النفسي، والطالع يبيّن طريقتك في الظهور والتعامل مع الحياة."
        )
        line4 = (
            f"بصورة مختصرة، يجمع هذا المزيج بين {sun_trait} "
            f"وبين نفس داخلية تحمل نبرة {moon_trait} "
            f"وطريقة ظهور تميل إلى {asc_trait}"
        )

    return {
        "line1": line1,
        "line2": line2,
        "line3": line3,
        "line4": line4,
    }


def build_report(name: str, gender: str, positions, cusps, angles, jd_ut: float = None) -> Dict[str, object]:
    element_scores = analyze_elements(positions)
    aspects = detect_major_aspects(positions)
    planets_table = planet_positions_table(positions)
    asteroids_table = calculate_additional_points(jd_ut, cusps) if jd_ut is not None else []
    asteroids_points_analysis = generate_asteroids_points_analysis(asteroids_table)
    welcome_message = generate_welcome_message(name, gender, positions, angles)

    general_analysis = generate_general_analysis(name, positions, angles, element_scores)
    chart_pattern = detect_chart_pattern(positions)
    core_analysis = generate_asc_sun_moon_analysis(positions, angles)
    planetary_analysis = generate_planetary_analysis(positions, aspects)
    houses_analysis = generate_houses_analysis(cusps, positions)
    dignity_summary = generate_dignity_summary(positions)
    aspects_analysis = generate_aspects_analysis(aspects)
    midpoints_analysis = generate_midpoints_analysis(positions, cusps, angles)
    supporting_techniques = generate_supporting_techniques(positions, cusps, angles, aspects, element_scores)

    strengths = generate_strengths(positions, angles, element_scores, aspects)
    notes = generate_growth_notes(positions, element_scores, aspects)
    creativity = generate_creativity(positions, angles, element_scores)
    challenges = generate_challenges(positions, aspects)

    sun = positions["Sun"]
    moon = positions["Moon"]
    asc_sign = str(angles["ASC_sign"])
    asc_degree = float(angles["ASC_degree"])
    mc_sign = str(angles["MC_sign"])
    mc_degree = float(angles["MC_degree"])

    intro = (
        f"هذه قراءة شخصية أولية للخريطة الخاصة بـ {name}. "
        "تعتمد هذه النسخة على الخريطة الأصلية: الطالع، الشمس، القمر، الكواكب، البيوت، الاتصالات الأساسية، وحدود بطليموس بصورة مبسطة. "
        "الهدف هو تقديم قراءة مفهومة تساعد على معرفة طبيعة الشخصية، مكامن القوة، مناطق النمو، مجالات الإبداع، والتحديات التي تحتاج إلى وعي."
    )

    summary = (
        "الخلاصة: الخريطة لا تختصر الإنسان في حكم واحد، بل تكشف طريقة عمل طاقته. "
        "عند فهم الطالع والشمس والقمر، ثم ربط الكواكب بالبيوت، تظهر الصورة أوضح: أين توجد القوة، أين يظهر الضغط، وأين يمكن أن يتحول التحدي إلى نضج. "
        "أفضل استخدام لهذه القراءة هو تحويلها إلى وعي عملي: تقوية الصفات الإيجابية، تهذيب الصفات المتعبة، اختيار البيئة المناسبة للإبداع، ومراقبة التحديات قبل أن تتحول إلى عوائق."
    )

    technical = {
        "asc": f"{asc_sign} {format_degree(asc_degree)}",
        "mc": f"{mc_sign} {format_degree(mc_degree)}",
        "sun": f"{sun.sign} {format_degree(sun.degree)} - البيت {sun.house} - حد {sun.term}",
        "moon": f"{moon.sign} {format_degree(moon.degree)} - البيت {moon.house} - حد {moon.term}",
        "elements": element_scores,
        "aspects": aspects[:12],
    }

    # توجيه الخطاب حسب الجنس المختار.
    intro = personalize_text(intro, gender)
    general_analysis = personalize_text(general_analysis, gender)
    chart_pattern["text"] = personalize_text(str(chart_pattern["text"]), gender)
    core_analysis = {k: personalize_text(v, gender) for k, v in core_analysis.items()}
    planetary_analysis = personalize_list(planetary_analysis, gender)
    asteroids_points_analysis = personalize_list(asteroids_points_analysis, gender)
    houses_analysis = personalize_list(houses_analysis, gender)
    dignity_summary = personalize_list(dignity_summary, gender)
    aspects_analysis = personalize_list(aspects_analysis, gender)
    midpoints_analysis = [
        {
            "title": group["title"],
            "items": personalize_list(group["items"], gender)
        }
        for group in midpoints_analysis
    ]
    supporting_techniques = personalize_list(supporting_techniques, gender)
    strengths = personalize_list(strengths, gender)
    notes = personalize_list(notes, gender)
    creativity = personalize_list(creativity, gender)
    challenges = personalize_list(challenges, gender)
    summary = personalize_text(summary, gender)

    return {
        "welcome_message": welcome_message,
        "intro": intro,
        "general_analysis": general_analysis,
        "planets_table": planets_table,
        "asteroids_table": asteroids_table,
        "chart_pattern": chart_pattern,
        "core_analysis": core_analysis,
        "planetary_analysis": planetary_analysis,
        "asteroids_points_analysis": asteroids_points_analysis,
        "houses_analysis": houses_analysis,
        "dignity_summary": dignity_summary,
        "aspects_analysis": aspects_analysis,
        "midpoints_analysis": midpoints_analysis,
        "supporting_techniques": supporting_techniques,
        "strengths": strengths,
        "notes": notes,
        "creativity": creativity,
        "challenges": challenges,
        "summary": summary,
        "technical": technical,
    }


# ============================================================
# الواجهة
# ============================================================

HTML = r"""
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
    <meta charset="UTF-8">
    <title>{{ title }}</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Tahoma, Arial, sans-serif;
            background: #f4f1ea;
            margin: 0;
            padding: 0;
            color: #2d2926;
            line-height: 1.9;
        }
        .container {
            max-width: 1050px;
            margin: 0 auto;
            padding: 18px;
        }
        .card {
            background: #fffdf8;
            border: 1px solid #ded4c4;
            border-radius: 16px;
            padding: 18px;
            margin-bottom: 16px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        }
        h1, h2, h3 {
            margin-top: 0;
            color: #3b2f2f;
        }
        h1 {
            text-align: center;
            font-size: 26px;
        }
        h2 {
            border-right: 5px solid #9b7b4f;
            padding-right: 10px;
            font-size: 21px;
        }
        label {
            display: block;
            margin-bottom: 5px;
            font-weight: bold;
        }
        input, select {
            width: 100%;
            box-sizing: border-box;
            padding: 10px;
            border-radius: 10px;
            border: 1px solid #c8bda9;
            background: #fff;
            font-size: 16px;
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 12px;
        }
        .grid2 {
            display: grid;
            grid-template-columns: repeat(2, 1fr);
            gap: 12px;
        }
        .buttons {
            display: flex;
            gap: 10px;
            margin-top: 14px;
        }
        .copy-report-btn {
            background: #3f5f45;
            color: #fff;
            width: 100%;
            margin: 8px 0 16px 0;
        }
        button, .clear-btn {
            border: none;
            border-radius: 12px;
            padding: 12px 18px;
            font-size: 16px;
            cursor: pointer;
            text-decoration: none;
            text-align: center;
        }
        button {
            background: #6f4e37;
            color: white;
            flex: 1;
        }
        .clear-btn {
            background: #d8c7ad;
            color: #2d2926;
            flex: 1;
        }
        .section {
            background: #fff;
            border-radius: 14px;
            padding: 14px;
            border: 1px solid #e6dccb;
            margin: 12px 0;
        }
        .item {
            margin-bottom: 10px;
            padding: 10px;
            background: #faf6ef;
            border-radius: 10px;
        }
        .warning {
            background: #fff3cd;
            border: 1px solid #f0d98c;
            border-radius: 12px;
            padding: 12px;
        }
        .technical {
            font-size: 14px;
            background: #f7f7f7;
            border-radius: 10px;
            padding: 12px;
            overflow-x: auto;
        }
        .muted {
            color: #6d6259;
            font-size: 14px;
        }
        .hidden {
            display: none;
        }
        @media (max-width: 800px) {
            .grid, .grid2 {
                grid-template-columns: 1fr;
            }
            h1 {
                font-size: 22px;
            }
        }
        @media print {
            .form-card, .buttons {
                display: none;
            }
            body {
                background: white;
            }
            .card {
                box-shadow: none;
                border: 1px solid #ddd;
            }
        }
    
        .app-subtitle {
            text-align: center;
            margin: -6px 0 4px 0;
            color: #6b5a46;
            font-size: 16px;
            line-height: 1.8;
            font-weight: 600;
        }
        .app-author {
            text-align: center;
            margin: 0 0 18px 0;
            color: #4b3828;
            font-size: 15px;
            line-height: 1.8;
            font-weight: 700;
        }


      .report-watermark {
        position: relative;
        overflow: hidden;
      }

      .report-watermark::before {
        content: "جميع الحقوق محفوظة للمطور astrologer.ab@";
        position: absolute;
        top: 8%;
        right: -10%;
        width: 120%;
        height: 120%;
        transform: rotate(-24deg);
        font-size: 28px;
        line-height: 3.2;
        color: rgba(80, 55, 35, 0.075);
        white-space: pre-wrap;
        pointer-events: none;
        z-index: 0;
        text-align: center;
      }

      .report-watermark > * {
        position: relative;
        z-index: 1;
      }

      .rights-footer {
        text-align: center;
        margin: 18px 0 8px 0;
        padding: 10px;
        font-size: 14px;
        color: #5f4936;
        font-weight: 700;
        border-top: 1px solid rgba(95, 73, 54, 0.18);
      }

</style>

    <script>
        async function loadCitiesForCountry() {
            const countrySelect = document.getElementById("country_code");
            const citySelect = document.getElementById("city_select");
            const manualBox = document.getElementById("manual_city_box");
            const manualInput = document.getElementById("city_manual");
            const selectedCountry = countrySelect.value;

            citySelect.innerHTML = "";
            const loadingOption = document.createElement("option");
            loadingOption.value = "";
            loadingOption.textContent = "جاري تحميل المدن...";
            citySelect.appendChild(loadingOption);

            try {
                const response = await fetch("/api/cities?country_code=" + encodeURIComponent(selectedCountry));
                const data = await response.json();

                citySelect.innerHTML = "";

                data.cities.forEach(function(cityName) {
                    const option = document.createElement("option");
                    option.value = cityName;
                    option.textContent = cityName;
                    citySelect.appendChild(option);
                });

                const other = document.createElement("option");
                other.value = "__manual__";
                other.textContent = "مدينة أخرى / أكتبها يدويًا";
                citySelect.appendChild(other);

                const currentCity = citySelect.getAttribute("data-selected");
                if (currentCity) {
                    let found = false;
                    for (let i = 0; i < citySelect.options.length; i++) {
                        if (citySelect.options[i].value === currentCity) {
                            citySelect.value = currentCity;
                            found = true;
                            break;
                        }
                    }
                    if (!found) {
                        citySelect.value = "__manual__";
                        manualBox.classList.remove("hidden");
                        manualInput.value = currentCity;
                    }
                }

                toggleManualCity();
            } catch (e) {
                // إذا تعذر الجلب، نبقي القائمة الموجودة أصلًا من السيرفر ولا نحذفها.
                let hasOther = false;
                for (let i = 0; i < citySelect.options.length; i++) {
                    if (citySelect.options[i].value === "__manual__") {
                        hasOther = true;
                        break;
                    }
                }
                if (!hasOther) {
                    const other = document.createElement("option");
                    other.value = "__manual__";
                    other.textContent = "مدينة أخرى / أكتبها يدويًا";
                    citySelect.appendChild(other);
                }
                toggleManualCity();
            }
        }

        function toggleManualCity() {
            const citySelect = document.getElementById("city_select");
            const manualBox = document.getElementById("manual_city_box");
            const manualInput = document.getElementById("city_manual");

            if (citySelect.value === "__manual__") {
                manualBox.classList.remove("hidden");
                manualInput.required = true;
            } else {
                manualBox.classList.add("hidden");
                manualInput.required = false;
                manualInput.value = "";
            }
        }

        document.addEventListener("DOMContentLoaded", function() {
            const countrySelect = document.getElementById("country_code");
            const citySelect = document.getElementById("city_select");

            if (countrySelect && citySelect) {
                loadCitiesForCountry();
                countrySelect.addEventListener("change", function() {
                    citySelect.setAttribute("data-selected", "");
                    document.getElementById("city_manual").value = "";
                    loadCitiesForCountry();
                });
                citySelect.addEventListener("change", toggleManualCity);
            }
        });
    </script>


    <script>
        function copyReportText() {
            const reportBox = document.getElementById("report_copy_area");
            if (!reportBox) return;

            const text = reportBox.innerText || reportBox.textContent || "";

            if (navigator.clipboard && window.isSecureContext) {
                navigator.clipboard.writeText(text).then(function() {
                    alert("تم نسخ التقرير");
                }).catch(function() {
                    fallbackCopyText(text);
                });
            } else {
                fallbackCopyText(text);
            }
        }

        function fallbackCopyText(text) {
            const temp = document.createElement("textarea");
            temp.value = text;
            temp.style.position = "fixed";
            temp.style.left = "-9999px";
            temp.style.top = "-9999px";
            document.body.appendChild(temp);
            temp.focus();
            temp.select();
            try {
                document.execCommand("copy");
                alert("تم نسخ التقرير");
            } catch (e) {
                alert("لم يتم النسخ تلقائيًا. ظلّل التقرير وانسخه يدويًا.");
            }
            document.body.removeChild(temp);
        }
    </script>

    {% if not report and not error %}
    <script>
        window.addEventListener("pageshow", function() {
            const fieldsToClear = ["name", "year", "month", "day", "hour", "minute", "city_manual"];
            fieldsToClear.forEach(function(fieldName) {
                const el = document.querySelector('[name="' + fieldName + '"]');
                if (el) { el.value = ""; }
            });

            const gender = document.querySelector('[name="gender"]');
            if (gender) { gender.value = ""; }

            const country = document.getElementById("country_code");
            if (country) { country.value = ""; }

            const city = document.getElementById("city_select");
            if (city) {
                city.innerHTML = '<option value="" selected disabled>اختر المدينة</option><option value="__manual__">مدينة أخرى / أكتبها يدويًا</option>';
                city.setAttribute("data-selected", "");
            }

            const manualBox = document.getElementById("manual_city_box");
            if (manualBox) { manualBox.classList.add("hidden"); }
        });
    </script>
    {% endif %}


    <!-- Google tag (gtag.js) -->
    <script async src="https://www.googletagmanager.com/gtag/js?id=G-2XZSMG55TG"></script>
    <script>
      window.dataLayer = window.dataLayer || [];
      function gtag(){dataLayer.push(arguments);}
      gtag('js', new Date());
      gtag('config', 'G-2XZSMG55TG');
    </script>


    <style>
      body, body * {
        -webkit-user-select: none !important;
        -moz-user-select: none !important;
        -ms-user-select: none !important;
        user-select: none !important;
        -webkit-touch-callout: none !important;
      }

      input, textarea, select, option, button {
        -webkit-user-select: auto !important;
        -moz-user-select: auto !important;
        -ms-user-select: auto !important;
        user-select: auto !important;
        -webkit-touch-callout: default !important;
      }

      .no-copy-note {
        font-size: 13px;
        opacity: 0.75;
        margin-top: 8px;
      }
    </style>

    <script>
      (function () {
        function blockEvent(e) {
          e.preventDefault();
          e.stopPropagation();
          return false;
        }

        document.addEventListener('contextmenu', blockEvent, true);
        document.addEventListener('copy', blockEvent, true);
        document.addEventListener('cut', blockEvent, true);

        document.addEventListener('paste', function(e) {
          const tag = (e.target && e.target.tagName || '').toLowerCase();
          if (!['input', 'textarea', 'select'].includes(tag)) {
            return blockEvent(e);
          }
        }, true);

        document.addEventListener('selectstart', function(e) {
          const tag = (e.target && e.target.tagName || '').toLowerCase();
          if (!['input', 'textarea', 'select', 'option'].includes(tag)) {
            return blockEvent(e);
          }
        }, true);

        document.addEventListener('dragstart', blockEvent, true);

        document.addEventListener('keydown', function(e) {
          const key = (e.key || '').toLowerCase();
          const ctrl = e.ctrlKey || e.metaKey;

          if (ctrl && ['a', 'c', 'x', 's', 'u', 'p'].includes(key)) {
            return blockEvent(e);
          }

          if (key === 'printscreen') {
            return blockEvent(e);
          }

          if (key === 'f12') {
            return blockEvent(e);
          }

          if (ctrl && e.shiftKey && ['i', 'j', 'c'].includes(key)) {
            return blockEvent(e);
          }
        }, true);
      })();
    </script>

</head>
<body>
<div class="container">
    <h1>{{ title }}</h1>
        <div class="app-subtitle">تحليل شامل للهوية، الطالع، الكواكب، البيوت، الكويكبات ونقاط النمو الذاتي</div>
        <div class="app-author">من إعداد الخبير الفلكي عباس الشباني</div>

    <div class="card form-card">
        <h2>بيانات الميلاد</h2>

        {% if not swisseph_available %}
        <div class="warning">
            مكتبة Swiss Ephemeris غير مثبتة. ثبّت المتطلبات:
            <br><b>pip install flask pyswisseph geonamescache</b>
        </div>
        {% endif %}

        {% if not geonames_available %}
        <div class="warning">
            مكتبة المدن العالمية غير مثبتة. ثبّت:
            <br><b>pip install geonamescache</b>
        </div>
        {% endif %}

        <form method="post" autocomplete="off">
            <div class="grid2">
                <div>
                    <label>الاسم</label>
                    <input name="name" value="{{ form.name }}" required autocomplete="new-password" autocorrect="off" autocapitalize="off" spellcheck="false">
                </div>
                <div>
                    <label>الجنس</label>
                    <select name="gender" autocomplete="new-password" required>
                        <option value="" {% if not form.gender %}selected{% endif %} disabled>اختر الجنس</option>
                        <option value="ذكر" {% if form.gender == "ذكر" %}selected{% endif %}>ذكر</option>
                        <option value="أنثى" {% if form.gender == "أنثى" %}selected{% endif %}>أنثى</option>
                    </select>
                </div>
            </div>

            <div class="grid">
                <div>
                    <label>سنة الميلاد</label>
                    <input type="number" name="year" value="{{ form.year }}" required autocomplete="new-password">
                </div>
                <div>
                    <label>شهر الميلاد</label>
                    <input type="number" name="month" value="{{ form.month }}" min="1" max="12" required autocomplete="new-password">
                </div>
                <div>
                    <label>يوم الميلاد</label>
                    <input type="number" name="day" value="{{ form.day }}" min="1" max="31" required autocomplete="new-password">
                </div>
            </div>

            <div class="grid2">
                <div>
                    <label>ساعة الميلاد</label>
                    <input type="number" name="hour" value="{{ form.hour }}" min="0" max="23" required autocomplete="new-password">
                    <p class="muted">الساعة بنظام 24 ساعة: 13 تعني 1 ظهرًا، و01 تعني 1 بعد منتصف الليل.</p>
                </div>
                <div>
                    <label>دقيقة الميلاد</label>
                    <input type="number" name="minute" value="{{ form.minute }}" min="0" max="59" required autocomplete="new-password">
                </div>
            </div>

            <div class="grid">
                <div>
                    <label>الدولة</label>
                    <select id="country_code" name="country_code" autocomplete="new-password" required>
                        <option value="" {% if not form.country_code %}selected{% endif %} disabled>اختر الدولة</option>
                        {% for c in countries %}
                            <option value="{{ c.code }}" {% if form.country_code == c.code %}selected{% endif %}>{{ c.name }}</option>
                        {% endfor %}
                    </select>
                </div>
                <div>
                    <label>المدينة</label>
                    <select id="city_select" name="city_select" data-selected="{{ form.city }}" autocomplete="new-password" required>
                        <option value="" {% if not form.city %}selected{% endif %} disabled>اختر المدينة</option>
                        {% for city_name in city_suggestions %}
                            <option value="{{ city_name }}" {% if form.city == city_name %}selected{% endif %}>{{ city_name }}</option>
                        {% endfor %}
                        <option value="__manual__">مدينة أخرى / أكتبها يدويًا</option>
                    </select>
                    <div id="manual_city_box" class="hidden" style="margin-top: 8px;">
                        <input id="city_manual" name="city_manual" value="{{ form.city_manual }}" placeholder="اكتب اسم المدينة هنا" autocomplete="new-password" autocorrect="off" autocapitalize="off" spellcheck="false">
                    </div>

                </div>
                <div>
                    <label>نظام البيوت</label>
                    <select name="house_system">
                        <option value="P" {% if form.house_system == "P" or not form.house_system %}selected{% endif %}>Placidus</option>
                        <option value="W" {% if form.house_system == "W" %}selected{% endif %}>Whole Sign</option>
                    </select>
                </div>
            </div>



            <div class="buttons">
                <button type="submit">استخراج التقرير</button>
                <a class="clear-btn" href="/">مسح البيانات</a>
            </div>
        </form>
    </div>

    {% if error %}
    <div class="card warning">
        {{ error }}
    </div>
    {% endif %}

    {% if report %}
    <div class="card">
        <h2>التقرير الشخصي</h2>
        

        <div id="report_copy_area" class="report-watermark">
        <div class="section">
            <h3>{{ report.welcome_message.line1 }}</h3>
            <p><strong>{{ report.welcome_message.line2 }}</strong></p>
            <p>{{ report.welcome_message.line3 }}</p>
            <p>{{ report.welcome_message.line4 }}</p>
        </div>

        <div class="section">
            <h3>المقدمة</h3>
            <p>{{ report.intro }}</p>
        </div>

        <div class="section">
            <h3>التحليل العام للخريطة</h3>
            <p>{{ report.general_analysis }}</p>
        </div>

        <div class="section">
            <h3>نمط توزيع الكواكب في الخريطة</h3>
            <p>{{ report.chart_pattern["text"] }}</p>
        </div>

        <div class="section">
            <h3>جدول مواقع الكواكب الأساسية</h3>
            <div class="data-table-wrap">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>الكوكب</th>
                            <th>البرج</th>
                            <th>الدرجة</th>
                            <th>البيت</th>
                            <th>الحد</th>
                            <th>الحركة / الحالة</th>
                            <th>الدستورية</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for row in report.planets_table %}
                        <tr>
                            <td>{{ row.name }}</td>
                            <td>{{ row.sign }}</td>
                            <td>{{ row.degree }}</td>
                            <td>{{ row.house }}</td>
                            <td>{{ row.term }}</td>
                            <td>{{ row.retro }}</td>
                            <td>{{ row.dignity }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>

        {% if report.asteroids_table %}
        <div class="section">
            <h3>جدول الكويكبات والنقاط المهمة</h3>
            <div class="data-table-wrap">
                <table class="data-table">
                    <thead>
                        <tr>
                            <th>النقطة</th>
                            <th>البرج</th>
                            <th>الدرجة</th>
                            <th>البيت</th>
                            <th>الحد</th>
                            <th>الحركة / الحالة</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for row in report.asteroids_table %}
                        <tr>
                            <td>{{ row.name }}</td>
                            <td>{{ row.sign }}</td>
                            <td>{{ row.degree }}</td>
                            <td>{{ row.house }}</td>
                            <td>{{ row.term }}</td>
                            <td>{{ row.retro }}</td>
                        </tr>
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% endif %}

        <div class="section">
            <h3>الطالع</h3>
            <p>{{ report.core_analysis.asc }}</p>
        </div>

        <div class="section">
            <h3>الشمس</h3>
            <p>{{ report.core_analysis.sun }}</p>
        </div>

        <div class="section">
            <h3>القمر</h3>
            <p>{{ report.core_analysis.moon }}</p>
        </div>

        <div class="section">
            <h3>تحليل الكواكب واحدًا تلو الآخر</h3>
            {% for item in report.planetary_analysis %}
                <div class="item">{{ item }}</div>
            {% endfor %}
        </div>

        <div class="section">
            <h3>تحليل الكويكبات والنقاط المهمة</h3>
            {% for item in report.asteroids_points_analysis %}
                <div class="item">{{ item }}</div>
            {% endfor %}
        </div>

        <div class="section">
            <h3>خلاصة دستورية الكواكب وانعكاسها على الشخصية</h3>
            {% for item in report.dignity_summary %}
                <div class="item">{{ item }}</div>
            {% endfor %}
        </div>

        <div class="section">
            <h3>تحليل البيوت الفلكية</h3>
            {% for item in report.houses_analysis %}
                <div class="item">{{ item }}</div>
            {% endfor %}
        </div>

        <div class="section">
            <h3>نقاط المنتصف حسب الموضوع</h3>
            {% for group in report.midpoints_analysis %}
                <h4>{{ group["title"] }}</h4>
                {% for item in group["items"] %}
                    <div class="item">{{ item }}</div>
                {% endfor %}
            {% endfor %}
        </div>

        <div class="section">
            <h3>تحليل الاتصالات الرئيسية</h3>
            {% for item in report.aspects_analysis %}
                <div class="item">{{ item }}</div>
            {% endfor %}
        </div>

        <div class="section">
            <h3>التقنيات المساندة في القراءة</h3>
            {% for item in report.supporting_techniques %}
                <div class="item">{{ item }}</div>
            {% endfor %}
        </div>

        <div class="section">
            <h3>الصفات الإيجابية في الخريطة</h3>
            {% for item in report.strengths %}
                <div class="item">{{ item }}</div>
            {% endfor %}
        </div>

        <div class="section">
            <h3>صفات تحتاج إلى اهتمام ووعي</h3>
            {% for item in report.notes %}
                <div class="item">{{ item }}</div>
            {% endfor %}
        </div>

        <div class="section">
            <h3>أين يمكن أن يكون الشخص مبدعًا؟</h3>
            {% for item in report.creativity %}
                <div class="item">{{ item }}</div>
            {% endfor %}
        </div>

        <div class="section">
            <h3>التحديات التي نخشى عليه منها</h3>
            {% for item in report.challenges %}
                <div class="item">{{ item }}</div>
            {% endfor %}
        </div>

        <div class="section">
            <h3>نصيحة النمو الذاتي</h3>
            <p>{{ report.summary }}</p>
        </div>
    </div>

    <div class="card">
        <h2>ملخص فني مختصر</h2>
        <div class="technical">
            <p><b>الطالع:</b> {{ report.technical.asc }}</p>
            <p><b>العاشر:</b> {{ report.technical.mc }}</p>
            <p><b>الشمس:</b> {{ report.technical.sun }}</p>
            <p><b>القمر:</b> {{ report.technical.moon }}</p>
            <p><b>العناصر:</b>
                نار {{ report.technical.elements["نار"] }} /
                تراب {{ report.technical.elements["تراب"] }} /
                هواء {{ report.technical.elements["هواء"] }} /
                ماء {{ report.technical.elements["ماء"] }}
            </p>

            <p><b>الاتصالات المختصرة:</b></p>
            {% if report.technical.aspects %}
                {% for a, b, asp, orb in report.technical.aspects %}
                    <div>{{ a }} {{ asp }} {{ b }} - الفارق {{ orb }}°</div>
                {% endfor %}
            {% else %}
                <div>لا توجد اتصالات رئيسية ضمن الأورب المعتمد في هذه النسخة.</div>
        
        </div>
    {% endif %}
        </div>
    </div>
    {% endif %}
</div>
<div class="no-copy-note" style="text-align:center;">حقوق القراءة محفوظة. النسخ اليدوي غير متاح داخل الموقع.</div>
<div class="rights-footer">جميع الحقوق محفوظة للمطور astrologer.ab@</div>
</body>
</html>
"""


# ============================================================
# Flask
# ============================================================

app = Flask(__name__)


@app.after_request
def add_no_cache_headers(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response



def default_form() -> Dict[str, str]:
    return {
        "name": "",
        "gender": "",
        "year": "",
        "month": "",
        "day": "",
        "hour": "",
        "minute": "",
        "country_code": "",
        "city": "",
        "city_select": "",
        "city_manual": "",
        "house_system": "P",
    }



@app.route("/api/cities")
def api_cities():
    country_code = request.args.get("country_code", "")
    cities = city_suggestions_for_country(country_code)

    # ضمان ظهور أهم المدن العراقية أولًا حتى لو تعطلت مكتبة المدن أو تأخرت.
    if country_code == "IQ":
        priority = [
            "بغداد", "النجف", "كربلاء", "الديوانية", "الشامية", "البصرة",
            "الموصل", "كركوك", "أربيل", "السليمانية", "الناصرية", "الحلة",
            "الرمادي", "العمارة", "السماوة", "الكوت", "بعقوبة", "تكريت",
            "دهوك", "الفلوجة", "سامراء"
        ]
        merged = []
        for x in priority + cities:
            if x not in merged:
                merged.append(x)
        cities = merged

    return jsonify({"cities": cities})


@app.route("/", methods=["GET", "POST"])
def index():
    form = default_form()
    report = None
    error = ""

    if request.method == "POST":
        form.update({k: request.form.get(k, form.get(k, "")) for k in form.keys()})

        try:
            name = form["name"].strip() or "صاحب الخريطة"
            gender = form["gender"]
            year = int(form["year"])
            month = int(form["month"])
            day = int(form["day"])
            hour = int(form["hour"])
            minute = int(form["minute"])
            country_code = form["country_code"]

            # المدينة قد تأتي من القائمة أو من حقل الكتابة اليدوية.
            city_choice = form.get("city_select", "").strip()
            city_manual = form.get("city_manual", "").strip()
            if city_choice == "__manual__":
                city_input = city_manual
            else:
                city_input = city_choice

            form["city"] = city_input

            city_info = find_city(country_code, city_input)
            if not city_info:
                raise RuntimeError(
                    "لم أجد المدينة داخل الدولة المختارة. جرّب كتابة اسم المدينة بالإنكليزية، "
                    "مثل Baghdad أو Najaf، أو اختر دولة أخرى إذا كانت المدينة تابعة لها."
                )

            lat = float(city_info["lat"])
            lon_geo = float(city_info["lon"])
            tz_name = str(city_info.get("timezone", ""))
            timezone = timezone_offset_for_birth(tz_name, year, month, day, hour, minute)

            positions, cusps, angles = calculate_chart(
                year=year,
                month=month,
                day=day,
                hour=hour,
                minute=minute,
                timezone=timezone,
                lat=lat,
                lon_geo=lon_geo,
                house_system=form["house_system"],
            )

            report = build_report(name, gender, positions, cusps, angles, angles.get("JD_UT"))

        except Exception as exc:
            error = f"حدث خطأ أثناء الحساب: {exc}"

    countries = build_country_list()
    city_suggestions = city_suggestions_for_country(form.get("country_code", ""))

    return render_template_string(
        HTML,
        title=APP_TITLE,
        form=form,
        report=report,
        error=error,
        countries=countries,
        city_suggestions=city_suggestions,
        swisseph_available=SWISSEPH_AVAILABLE,
        geonames_available=GEONAMESCACHE_AVAILABLE,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    print("تشغيل تطبيق قراءة الخريطة الشخصية V4.9 Railway Final")
    print(f"افتح الرابط المحلي: http://127.0.0.1:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
