#!/usr/bin/env python3
"""
生成所有表情模版的示例图片脚本
使用指定的模板图片生成每个表情的示例，并保存到对应的模版目录下
"""

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict

from meme_generator import get_memes
from meme_generator.utils import run_sync


def load_template_image(image_path: str) -> bytes:
    """加载模板图片"""
    with open(image_path, 'rb') as f:
        return f.read()


def get_default_args(meme) -> Dict[str, Any]:
    """获取表情的默认参数"""
    if meme.params_type.args_type:
        # 使用第一个示例参数
        if meme.params_type.args_type.args_examples:
            from meme_generator.compat import model_dump
            return model_dump(meme.params_type.args_type.args_examples[0])
        # 如果没有示例，创建默认参数
        else:
            from meme_generator.compat import model_dump
            return model_dump(meme.params_type.args_type.args_model())
    return {}


def get_default_texts(meme) -> list[str]:
    """获取表情的默认文字"""
    if meme.params_type.default_texts:
        return meme.params_type.default_texts.copy()
    elif meme.params_type.min_texts > 0:
        # 生成默认文字
        return [f"示例文字{i+1}" for i in range(meme.params_type.min_texts)]
    return []


async def generate_meme_example(meme, template_image: bytes, output_dir: Path):
    """生成单个表情的示例图片"""
    try:
        print(f"正在生成 {meme.key} 的示例图片...")
        
        # 准备参数
        images = [template_image] * meme.params_type.min_images
        texts = get_default_texts(meme)
        args = get_default_args(meme)
        
        # 生成表情
        result = await run_sync(meme)(
            images=images,
            texts=texts,
            args=args
        )
        
        # 保存到对应目录
        meme_dir = Path(__file__).parent / "meme_generator" / "memes" / meme.key
        meme_dir.mkdir(exist_ok=True)
        
        # 确定文件扩展名
        content = result.getvalue()
        if content.startswith(b'GIF'):
            ext = '.gif'
        elif content.startswith(b'\xff\xd8\xff'):
            ext = '.jpg'
        elif content.startswith(b'\x89PNG'):
            ext = '.png'
        else:
            ext = '.gif'  # 默认使用gif
        
        example_path = meme_dir / f"example{ext}"
        with open(example_path, 'wb') as f:
            f.write(content)
        
        print(f"✓ {meme.key} 示例图片已保存到: {example_path}")
        return True
        
    except Exception as e:
        print(f"✗ 生成 {meme.key} 示例图片失败: {e}")
        return False


async def main():
    """主函数"""
    # 检查模板图片是否存在
    template_path = "/home/devbox/project/meme-generator/test_image/avatar.jpg"
    if not Path(template_path).exists():
        print(f"错误: 模板图片不存在: {template_path}")
        sys.exit(1)
    
    # 加载模板图片
    template_image = load_template_image(template_path)
    print(f"已加载模板图片: {template_path}")
    
    # 获取所有表情
    memes = get_memes()
    print(f"找到 {len(memes)} 个表情模版")
    
    # 生成示例图片
    success_count = 0
    total_count = len(memes)
    
    for meme in memes:
        success = await generate_meme_example(meme, template_image, Path(__file__).parent)
        if success:
            success_count += 1
    
    print(f"\n生成完成!")
    print(f"成功: {success_count}/{total_count}")
    print(f"失败: {total_count - success_count}/{total_count}")


if __name__ == "__main__":
    asyncio.run(main())
