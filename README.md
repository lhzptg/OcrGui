# OCR-GUI-demo

#### 介绍
图像文字识别OCR工具v1.0，含GUI界面。



#### 软件架构
- GUI 基于 [PyQt5](https://pypi.org/project/PyQt5/) + [labelme](https://github.com/wkentaro/labelme) 实现
- OCR 基于 [PaddleOCR](https://gitee.com/paddlepaddle/PaddleOCR/) 实现
- icons 来源于 [material-design-icons](https://github.com/google/material-design-icons)

### 功能特性
- 文本区域检测+文字识别
- 文本区域可视化
- 文字内容列表
- 图像、文件夹加载
- 图像滚轮缩放查看
- 复制文本识别结果

#### 使用说明
运行以下命令，即可启动软件。
```shell
python main.py
```
使用流程：
1. 打开图片 
2. 选择语言模型（默认ch中文）
3. 选择文本检测+识别
4. 点击开始按钮
5. 检测完的文本区域会自动画框，并在右侧识别结果列表中显示。

#### TODO List
- 绘制区域、编辑区域
- 增加自主框选
- 增加版面分析
- 增加自动翻译
- 增加程序打包
- 增加不同格式保存