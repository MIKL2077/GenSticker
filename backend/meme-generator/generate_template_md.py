cd /home/devbox/project/meme-generator && python3 -c "
import os
import re
import ast
from pathlib import Path
from collections import Counter

def extract_meme_info(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 查找add_meme调用
        add_meme_match = re.search(r'add_meme\(\s*([^)]+)\s*\)', content, re.DOTALL)
        if not add_meme_match:
            return None
            
        # 解析参数
        args_str = add_meme_match.group(1)
        
        # 提取模板名称
        name_match = re.search(r'\"([^\"]+)\"', args_str)
        template_name = name_match.group(1) if name_match else 'unknown'
        
        # 提取各种参数
        min_images = re.search(r'min_images\s*=\s*(\d+)', args_str)
        max_images = re.search(r'max_images\s*=\s*(\d+)', args_str)
        min_texts = re.search(r'min_texts\s*=\s*(\d+)', args_str)
        max_texts = re.search(r'max_texts\s*=\s*(\d+)', args_str)
        keywords = re.search(r'keywords\s*=\s*\[([^\]]+)\]', args_str)
        default_texts = re.search(r'default_texts\s*=\s*\[([^\]]+)\]', args_str)
        
        # 清理关键词和默认文本
        keywords_clean = keywords.group(1) if keywords else ''
        if keywords_clean:
            keywords_clean = keywords_clean.replace('\"', '').replace(\"'\", '')
        
        default_texts_clean = default_texts.group(1) if default_texts else ''
        if default_texts_clean:
            default_texts_clean = default_texts_clean.replace('\"', '').replace(\"'\", '')
        
        return {
            'name': template_name,
            'min_images': int(min_images.group(1)) if min_images else 0,
            'max_images': int(max_images.group(1)) if max_images else 0,
            'min_texts': int(min_texts.group(1)) if min_texts else 0,
            'max_texts': int(max_texts.group(1)) if max_texts else 0,
            'keywords': keywords_clean,
            'default_texts': default_texts_clean
        }
    except Exception as e:
        print(f'Error processing {file_path}: {e}')
        return None

# 遍历所有模板目录
memes_dir = Path('meme_generator/memes')
templates = []

for template_dir in memes_dir.iterdir():
    if template_dir.is_dir():
        init_file = template_dir / '__init__.py'
        if init_file.exists():
            info = extract_meme_info(init_file)
            if info:
                templates.append(info)

# 按名称排序
templates.sort(key=lambda x: x['name'])

# 统计信息
total_templates = len(templates)
image_only = len([t for t in templates if t['min_texts'] == 0 and t['max_texts'] == 0])
text_only = len([t for t in templates if t['min_images'] == 0 and t['max_images'] == 0])
mixed = len([t for t in templates if t['min_images'] > 0 and t['min_texts'] > 0])

# 生成markdown文档
markdown_content = f'''# 表情模板输入要求文档

本文档整理了项目中所有表情模板的输入要求。

## 统计信息

- **总模板数量**: {total_templates} 个
- **仅需图片**: {image_only} 个
- **仅需文本**: {text_only} 个  
- **需要图片+文本**: {mixed} 个

## 模板列表

'''

for template in templates:
    # 确定输入类型
    input_type = []
    if template['min_images'] > 0 or template['max_images'] > 0:
        input_type.append('图片')
    if template['min_texts'] > 0 or template['max_texts'] > 0:
        input_type.append('文本')
    
    input_type_str = ' + '.join(input_type) if input_type else '无'
    
    markdown_content += f'''### {template['name']}

**类型**: {input_type_str}

**关键词**: {template['keywords'] or '无'}

**输入要求**:
- 图片数量: {template['min_images']}-{template['max_images']} 张
- 文本数量: {template['min_texts']}-{template['max_texts']} 个

'''
    if template['default_texts']:
        markdown_content += f'**默认文本**: {template[\"default_texts\"]}\n'
    
    markdown_content += '\n---\n\n'

# 保存到文件
with open('template.md', 'w', encoding='utf-8') as f:
    f.write(markdown_content)

print(f'已生成 template.md 文件，包含 {len(templates)} 个模板')
print(f'统计: 仅图片 {image_only} 个, 仅文本 {text_only} 个, 混合 {mixed} 个')
"