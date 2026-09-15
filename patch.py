import sys

with open('templates/dashboard.html', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Fix .id-chip color
content = content.replace('            color: #fda4af;\n', '')

# 2. Fix the id-chip in the table
content = content.replace('<td class=\"id-chip\">${escapeHtml(item.student_id)}</td>', '<td><span class=\"id-chip\">${escapeHtml(item.student_id)}</span></td>')

# 3. Rename Late Comers to Late Entry and add badge
content = content.replace('<h3><i class=\"fas fa-clock\"></i> Late Comers</h3>', '<h3><i class=\"fas fa-clock\"></i> Late Entry</h3>\n                    <div style=\"display:flex;gap:8px;align-items:center;\">\n                        <span class=\"badge\" id=\"late-total-badge\">0</span>\n                    </div>')
content = content.replace('<span id=\"late-dept-title\">Late Comers</span>', '<span id=\"late-dept-title\">Late Entry</span>')
content = content.replace('No late comers in this department', 'No late entries in this department')

# 4. Add the total calculation to renderLateChips
original_js = """            const container = document.getElementById('late-chips');
            if (!container) return;"""
new_js = """            const container = document.getElementById('late-chips');
            const badge = document.getElementById('late-total-badge');
            if (!container) return;

            let totalLate = 0;
            Object.values(map).forEach(v => totalLate += v);
            if (badge) badge.textContent = String(totalLate);"""
content = content.replace(original_js, new_js)

with open('templates/dashboard.html', 'w', encoding='utf-8') as f:
    f.write(content)

print('Done!')
