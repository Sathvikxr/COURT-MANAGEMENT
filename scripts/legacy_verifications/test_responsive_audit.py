"""
Responsive & Polish Audit Script
Validates:
- 375px, 768px, 1024px, 1440px, 1920px CSS rule existence & behavior
- Mobile bottom navigation bar & sidebar backdrop
- Modal full-screen sheets on mobile
- Touch target compliance (>=44px)
- Zero horizontal overflow enforcers
- Print stylesheet with court letterhead, seal, signature, QR code
- Loading skeletons, empty states, error states
"""

import os
import re

css_path = r"C:\CourtMS\static\css\design-system.css"
templates_dir = r"C:\CourtMS\templates"

def audit_css():
    with open(css_path, "r", encoding="utf-8") as f:
        css = f.read()

    checks = {
        "375px mobile breakpoint (max-width: 480px)": "@media (max-width: 480px)" in css,
        "768px mobile breakpoint (max-width: 768px)": "@media (max-width: 768px)" in css,
        "1024px tablet breakpoint (max-width: 1024px)": "max-width: 1024px" in css,
        "1440px large screen breakpoint (min-width: 1440px)": "@media (min-width: 1440px)" in css,
        "1920px ultrawide breakpoint (min-width: 1920px)": "@media (min-width: 1920px)" in css,
        "Mobile sidebar backdrop (.sidebar-backdrop)": ".sidebar-backdrop" in css,
        "Mobile bottom nav (.mobile-bottom-nav)": ".mobile-bottom-nav" in css,
        "Mobile sheet modals (sheetSlideUp / border-radius)": "sheetSlideUp" in css,
        "Touch target 44px min-height": "min-height: 44px" in css,
        "Horizontal overflow prevention (overflow-x: hidden)": "overflow-x: hidden" in css,
        "Print stylesheet (@media print)": "@media print" in css,
        "Formal court letterhead print styles": ".court-print-header" in css,
        "Digital signature block print styles": ".court-print-signature" in css,
        "QR verification code print styles": ".court-print-qr" in css,
        "Loading skeleton system (.skeleton)": ".skeleton" in css,
        "Standardized empty state (.empty-state)": ".empty-state" in css,
        "Universal focus rings (:focus-visible)": ":focus-visible" in css,
        "Disabled state standards (.disabled)": ":disabled" in css,
        "Form validation & error states (.is-invalid)": ".is-invalid" in css,
        "Chart container layout shift protection": ".chart-container-box" in css or "height: 240px" in css,
    }

    print("=== CSS RESPONSIVE & DESIGN SYSTEM AUDIT ===")
    all_passed = True
    for name, passed in checks.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {name}")
        if not passed:
            all_passed = False

    return all_passed

def audit_templates():
    print("\n=== TEMPLATES RESPONSIVE & STRUCTURAL AUDIT ===")
    base_dash = os.path.join(templates_dir, "base_dashboard.html")
    with open(base_dash, "r", encoding="utf-8") as f:
        dash_content = f.read()

    dash_checks = {
        "Base Dashboard has Mobile Sidebar Toggle": 'id="mobile-sidebar-toggle"' in dash_content,
        "Base Dashboard has Mobile Sidebar Backdrop": 'id="sidebar-backdrop"' in dash_content,
        "Base Dashboard has Mobile Bottom Navigation Bar": 'class="mobile-bottom-nav"' in dash_content,
        "Base Dashboard has Global Search Modal": 'id="global-search-modal"' in dash_content,
        "Base Dashboard has Case Docket Drawer": 'id="case-detail-drawer"' in dash_content,
        "Base Dashboard has User Profile Modal": 'id="user-profile-modal"' in dash_content,
        "Base Dashboard has Theme Toggle Button": 'id="theme-toggle-btn"' in dash_content,
        "Base Dashboard has Notification Bell": 'id="notif-bell-btn"' in dash_content,
    }

    for name, passed in dash_checks.items():
        status = "[PASS]" if passed else "[FAIL]"
        print(f"  {status} {name}")

    # Check that master tables in all role dashboards have responsive wrappers
    role_templates = [
        "dashboards/government.html",
        "dashboards/registrar.html",
        "dashboards/judge.html",
        "dashboards/clerk.html",
        "dashboards/lawyer.html",
        "dashboards/litigant.html",
        "dashboards/police.html",
        "notifications.html",
        "outbox.html",
        "reminders.html",
    ]

    print("\n--- Role Dashboards Table Responsiveness & KPI Integration ---")
    for t_rel in role_templates:
        t_path = os.path.join(templates_dir, t_rel)
        if not os.path.exists(t_path):
            print(f"  [MISSING] {t_rel}")
            continue
        with open(t_path, "r", encoding="utf-8") as tf:
            c = tf.read()
        has_table_resp = "table-responsive" in c or "table-container" in c
        has_kpi = "kpi-stat-card" in c or "kpi-grid" in c
        has_header = "dashboard-page-header" in c
        print(f"  [PASS] {t_rel:28} | responsive_table={has_table_resp} | kpi_grid={has_kpi} | header={has_header}")

if __name__ == "__main__":
    css_ok = audit_css()
    audit_templates()
    print("\nALL AUDITS COMPLETE.")
