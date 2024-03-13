import cv2
import numpy as np
import glob
import os
from numpy.linalg import inv


# Первая версия модуля для калибровки камер, необходимо добавить нахождение координат по известному размеру объекта в мировой СК
class CameraCalibrator:
    def __init__(self, board_size, frame_size, folder_path):
        self.board_size = board_size
        self.frame_size = frame_size
        self.path = folder_path  # Путь к папке с изображениями доски
        self.images = glob.glob(self.path + '*.jpg')
        self.found_map = False
        self.map_x = None  # Параметры необходимые для устранения дисторсии
        self.map_y = None
        self.new_cam_matrix = None
        self.roi = None

    def _find_corners(self):  # Вспомогательная функция для нахождения углов шахматной доски
        obj_points = []
        img_points = []
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.001)
        # Задаем массив координат углов доски
        objp = np.zeros((self.board_size[0] * self.board_size[1], 3), np.float32)
        objp[:, :2] = np.mgrid[0:self.board_size[0], 0:self.board_size[1]].T.reshape(-1, 2)

        for image in self.images:
            img = cv2.imread(image)
            gray = cv2.cvtColor(img, cv2.COLOR_BGRA2GRAY)
            corners_found, corners = cv2.findChessboardCorners(gray, self.board_size, None)
            if corners_found:
                obj_points.append(objp)
                corners_refined = cv2.cornerSubPix(gray, corners, (11, 11), (-1, -1), criteria)
                img_points.append(corners_refined)
                # Заполняем массивы координат точек на изображении и доске, чтобы на их основе выполнить калибровку
                cv2.drawChessboardCorners(img, self.board_size, corners_refined, corners_found)  # Рисуем углы на изображении для проверки
                cv2.imshow('img', img)
                cv2.waitKey(0)
        cv2.destroyAllWindows()
        return obj_points, img_points

    def undistort(self, img, cam_matrix, dist):  # Функция для исправления дисторсии
        h, w = img.shape[:2]
        if not self.found_map:  # Вычисляем карту для устранения дисторсии только один раз, чтобы не пересчитывать ее для каждого изображения
            self.new_cam_matrix, self.roi = cv2.getOptimalNewCameraMatrix(cam_matrix, dist, (w, h), 1, (w, h))
            self.map_x, self.map_y = cv2.initUndistortRectifyMap(cam_matrix, dist, None, self.new_cam_matrix, self.frame_size, 5)
            self.found_map = True
        undist_img = cv2.remap(img, self.map_x, self.map_y, cv2.INTER_LINEAR)
        x, y, w, h = self.roi  # Устраняем дисторсию и обрезаем изображение до нужных размеров
        undist_img = undist_img[y:y + h, x:x + w]
        cv2.imshow('undist', undist_img)
        cv2.waitKey(0)
        cv2.destroyAllWindows()
        return undist_img

    def calibrate(self):  # Получение внутренних параметров камеры
        obj_points, img_points = self._find_corners()
        # Получаем матрицу внутренних параметров и коэффициенты дисторсии после детекции шахматной доски
        rep_error, cam_matrix, dist_coeffs, rvecs, tvecs = cv2.calibrateCamera(obj_points, img_points, self.frame_size,
                                                                               None, None)

        cur_folder = os.path.dirname(os.path.abspath(__file__))
        param_path = os.path.join(cur_folder, 'results', 'intrinsics.npz')
        np.savez(param_path,  # Сохраняем внутренние параметры
                 rep_error=rep_error,
                 cam_matrix=cam_matrix,
                 dist_coeffs=dist_coeffs)
        return cam_matrix, dist_coeffs

    def pose_estimation(self, world_points, img_points, cam_matrix, dist_coeffs):  # Нахождение внешних параметров камеры
        # По нескольким (3 и более) точкам в мировой системе координат и их соответствиям на изображении вычисляем параметры для перехода из мировой СК в СК камеры
        rvec, tvec = cv2.solvePnP(world_points, img_points, cam_matrix, dist_coeffs)

        cur_folder = os.path.dirname(os.path.abspath(__file__))
        param_path = os.path.join(cur_folder, 'results', 'extrinsics.npz')
        np.savez(param_path,  # Сохраняем внешние параметры
                 rvecs=rvec, tvecs=tvec)
        return rvec, tvec

    def get_world_coords(self, cam_matrix, rvec, tvec, z_w_coord, img_point):  # Получаем координаты точки на плоскости в мировой СК по координатам точки на изображении
        # Для получения координат необходимо указать координату Z в мировой СК (то есть ноль для точек, находящихся на полу, если плоскость XY мировой СК совпадает с полом)
        rotation_mat, _ = cv2.Rodrigues(rvec)  # Переводим вектор поворота в матрицу поворота
        img_p = np.array([img_point[0], img_point[1], 1])
        left_side_mat = inv(rotation_mat) @ inv(cam_matrix) @ img_p
        right_side_mat = inv(rotation_mat) @ tvec  # Вычисления согласно формуле проецирования точки пространства на изображение
        scale = (z_w_coord + right_side_mat[2]) / left_side_mat[2]  # Вычисляем параметр, отвечающий за масштаб
        world_point = inv(rotation_mat) @ (scale * inv(cam_matrix) @ img_p - tvec)  # Получаем реальные координаты точки на плоскости
        return world_point

