# -*- coding: UTF-8 -*-
# @Time : 04/03/2018
# @File : dict2xml.py
# @Author: Jian <jian@mltalker.com>
from __future__ import division
from __future__ import unicode_literals
from __future__ import print_function
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom

####################################################
# <AntProxy>
#   <admin>
#     <user token='***'>***</user>
#   </admin>
# </AntProxy>
####################################################
def dict_2_xml(input_dict, root_tag):
  root_name = ET.Element(root_tag)
  for (k, v) in input_dict.items():
    parent_elem = ET.SubElement(root_name, k)
    for sub_v in v:
      child_elem = ET.SubElement(parent_elem, sub_v[0])
      child_elem.text = sub_v[1]
      child_elem.attrib = sub_v[2]

  return root_name


def output_xml(root, output_file):
  rough_string = ET.tostring(root, 'utf-8')
  reared_content = minidom.parseString(rough_string)
  with open(output_file, 'w+') as fs:
    reared_content.writexml(fs, addindent=" ", newl="\n", encoding="utf-8")
  return True


def read_xml(input_file):
  tree = ET.parse(input_file)
  dict_new = {}
  for key, valu in enumerate(tree.getroot()):
    list_init = []
    for item in valu:
      list_init.append([item.tag, item.text, item.attrib])

    dict_new[valu.tag] = list_init
  return dict_new


# content = read_xml('/Users/jian/Downloads/secret.xml')
# if 'admin' in content:
#   for cc in content['admin']:
#     if cc[1] == 'zhangjian':
#       cc[2]['token'] = 'jjjjj'
#
# xml_root = dict_2_xml(content, 'AntProxy')
#
# output_xml(xml_root, '/Users/jian/Downloads/zz.xml')