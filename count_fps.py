import json
import ast

def fps_count(filename):
    with open(filename, 'r') as file:
        fps_list = None
        for i, line in enumerate(file):
            line = line.rstrip()
            left_brack = line.find('{')
            s = line[left_brack:]
            fps_dict = ast.literal_eval(s)
            for src_id in fps_dict:
                fps_list = fps_dict[src_id]
                print(f'{line[:left_brack]} {sum(fps_list) / len(fps_list)}')


def gui_fps_count(file_name):
    with open(file_name, 'r') as file:
        fps_list = None
        for i, line in enumerate(file):
            line = line.rstrip()
            left_brack = line.find('{')
            s = line[left_brack:]
            fps_dict = ast.literal_eval(s)
            for src_id in fps_dict:
                fps_list = [el for el in fps_dict[src_id]]
                print(f'{line[:left_brack]} {sum(fps_list) / len(fps_list)}')



if __name__ == '__main__':
    file_name = 'controller_fps10obj_2c.txt'
    print(fps_count(file_name))
    print(gui_fps_count('gui_fps_10o_2c.txt'))
