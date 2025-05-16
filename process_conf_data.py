import numpy as np
import json
from matplotlib import pyplot as plt


def process(filename):
    heights = []
    confs = []
    with open(filename, 'r') as file:
        src_heights = []
        src_confs = []
        for line in file:
            if line == '\n':
                heights.append(src_heights)
                confs.append(src_confs)
                src_heights = []
                src_confs = []
                continue
            line = line.rstrip()
            left_brack = line.find('[')
            right_brack = line.find(']')
            if left_brack == -1 or right_brack == -1:
                continue
            coords = json.loads(line[left_brack:right_brack+1])
            print(coords)
            src_heights.append(coords[3] - coords[1])
            conf_idx = line.find('Conf: ') + len('Conf: ')
            src_confs.append(float(line[conf_idx:]))
    return heights, confs


def plot_graphs(heights, confs):
    for src_h, src_conf in zip(heights, confs):
        print(src_h)
        h_arr = np.asarray(src_h)
        # print(h_arr[0], h_arr[1])
        # h_arr = h_arr / (500 / 1280)
        # print(h_arr[0], h_arr[1])
        c_arr = np.asarray(src_conf)
        fig = plt.scatter(h_arr, c_arr)
        min_h = min(h_arr)
        print(min_h)
        lim_x = min_h // 200
        ax = fig.axes
        ax.minorticks_on()
        plt.xlabel('Normalized height')
        plt.ylabel('Confidence')
        plt.grid(True)
        plt.xlim(left=200 * lim_x)
        plt.ylim(bottom=0, top=1.0)
        plt.show()


if __name__ == '__main__':
    file_name = 'w_o_lost_objects_file.txt'
    h, c = process(file_name)
    print(len(h), h)
    print(len(c), c)
    plot_graphs(h, c)
    print(len(h), h[0])
    print(len(c), c[0])
