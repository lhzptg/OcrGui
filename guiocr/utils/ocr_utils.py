# -*- coding:utf-8 -*-
"""
基于paddleocr进行OCR识别、版面分析
Author: ZhangSY
Created time:2021/12/1 20:33
"""
from paddleocr import PaddleOCR, draw_ocr
from paddleocr import PPStructure,draw_structure_result,save_structure_res
# 显示结果
from PIL import Image
import os

def ocr(img_path='./imgs/11.jpg',use_angle=True,cls=True, lan="ch"):
    # Paddleocr目前支持的多语言语种可以通过修改lang参数进行切换
    # 例如`ch`, `en`, `fr`, `german`, `korean`, `japan`
    ocr = PaddleOCR(use_angle_cls=use_angle, lang=lan)  # need to run only once to download and load model into memory
    result = ocr.ocr(img_path, cls=cls)
    for line in result:
        print(line)
    return result

def vis_ocr_result(img_path="",result=None,save_folder = './output/'):
    image = Image.open(img_path).convert('RGB')
    boxes = [line[0] for line in result]
    txts = [line[1][0] for line in result]
    scores = [line[1][1] for line in result]
    im_show = draw_ocr(image, boxes, txts, scores, font_path='./fonts/simfang.ttf')
    im_show = Image.fromarray(im_show)
    im_show.save(os.path.join(save_folder,'result_ocr.jpg'))
    return im_show

"""
版面分析
"""
# table_engine = PPStructure(show_log=True)
#
# def structure_analysis(img_path='./table/paper-image.jpg',save_folder = './output/'):
#     img = cv2.imread(img_path)
#     result = table_engine(img)
#     save_structure_res(result, save_folder,os.path.basename(img_path).split('.')[0])
#     for line in result:
#         line.pop('img')
#         print(line)
#     return result
#
# def vis_structure_result(img_path,result,save_folder = './output/'):
#     font_path = './fonts/simfang.ttf' # PaddleOCR下提供字体包
#     image = Image.open(img_path).convert('RGB')
#     im_show = draw_structure_result(image, result,font_path=font_path)
#     im_show = Image.fromarray(im_show)
#     im_show.save(os.path.join(save_folder,'result_struct.jpg'))
#     return im_show

# For Test
if __name__=="__main__":
    img_path = r'D:\Projects\DemoGUI\test_imgs\00056221.jpg'
    result = ocr(img_path)
    vis_ocr_result(img_path,result)

    # result2 = structure_analysis(img_path)
    # vis_structure_result(img_path,result2)

