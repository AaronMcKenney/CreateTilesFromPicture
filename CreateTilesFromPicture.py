from PIL import Image
from sklearn.cluster import KMeans
import argparse
import os
import os.path
import re
import math

LOG_NAME = 'CreateTilesFromPicture_LOG.txt'
WARN = 'WARN'
ERR = 'ERR'

X = 0
Y = 1

R = 0
G = 1
B = 2

NO_DBLK = 0
ACROSS_TILE_DBLK = 1
EQUAL_BOUNDS_DBLK = 2

g_do_log = False
g_log_file = None

class Tile:
	def __init__(self, im, tile_pos, id):
		self.im = im
		self.x = tile_pos[X]
		self.y = tile_pos[Y]
		self.id = id
		self.cluster_id = 0

def ParseCommandLineArgs():
	in_def = './in.png'
	out_def = './out'
	size_def = '(0,0)'
	dblk_def = 1
	clusters_def = 1
	
	log_def = False
	
	prog_desc = ('Given a path to an image, ' 
		'as well as a crop size in terms of (width in pixels, height in pixels), ' 
		'take apart a picture, and create multiple "tiles", '
		'which will be deposited in the given out directory. '
		'NOTE 1: If the image size is not divisible by the crop size, "partial tiles" will not be output. '
		'NOTE 2: This program will not produce good results for lossy codecs such as jpeg')
	in_help = ('Path to the image that will have tiles made out of it. '
		'The name should include the extension, which dictates the image format of the output. '
		'Default: ' + in_def)
	out_help = ('Path to the directory which will contain the output tiles. '
		'Default: ' + out_def)
	size_help = ('The width and height (comma-separated) of each tile to be taken from the image. '
		'Example formats: "1,2", "(1,2)". '
		'Default: ' + size_def)
	clusters_help = ('If the number of clusters provided is greater than 1, a clustering algorithm '
		'will be used to organize the tiles into n directories of like images. '
		'Default: ' + str(clusters_def))
	dblk_help = ('The deblock mode. '
		'' + str(NO_DBLK) + ': No deblocking. '
		'' + str(ACROSS_TILE_DBLK) + ': Some deblocking: average pixels between two tile boundaries. '
		'' + str(EQUAL_BOUNDS_DBLK) + ': Most deblocking: average pixels across all of a given tile\'s boundaries. '
		'Default: ' + str(dblk_def))
	log_help = ('If set, log warnings and errors to "' + LOG_NAME + '" file. '
		'If not set, only report errors to stdout. '
		'Default: ' + str(log_def))
	no_log_help = ('If set, disable logging. Default: ' + str(not log_def))
	
	parser = argparse.ArgumentParser(description = prog_desc)
	parser.add_argument('--in_im_path',   '-i', type = str,                           help = in_help)
	parser.add_argument('--out_dir_path', '-o', type = str,                           help = out_help)
	parser.add_argument('--crop_size',    '-s', type = str,                           help = size_help)
	parser.add_argument('--num_clusters', '-c', type = int,                           help = dblk_help)
	parser.add_argument('--dblk_mode',    '-d', type = int,                           help = dblk_help)
	parser.add_argument('--log',          '-l', dest = 'log', action = 'store_true',  help = log_help)
	parser.add_argument('--no-log',             dest = 'log', action = 'store_false', help = no_log_help)
	
	parser.set_defaults(crop_size = size_def, in_im_path = in_def, out_dir_path = out_def, dblk_mode = dblk_def, num_clusters = clusters_def, log = log_def)

	args = parser.parse_args()
	
	return args

def SetupLogging(do_log):
	global g_do_log, g_log_file
	
	g_do_log = do_log
	if g_do_log:
		g_log_file = open(LOG_NAME, 'w')
	
	return
		
def Log(level, statement):
	global g_do_log, g_log_file
	
	log_line = level + ': ' + statement + '\n'
	if g_do_log:
		g_log_file.write(log_line)
	elif level == ERR:
		print(log_line)
	
	return

def CloseLog():
	global g_do_log, g_log_file
	
	if g_do_log:
		g_log_file.close()
		
		if(os.path.getsize(LOG_NAME)):
			print('Encountered warnings/errors. See ' + LOG_NAME + ' for details')
		else:
			print('No errors encountered whatsoever')

	return
	
def GetImageFromPath(im_path):
	im = None
	
	try:
		im = Image.open(im_path)
	except OSError as err:
		Log(ERR, str(err))
	
	return im

def GetTupleFromStr(tuple_str):
	#allow for various ways of sending in tuples, including "1,1" and "(1,1)"
	tuple_str = re.sub('[(){}<>]', '', tuple_str)
	tuple_str_arr = re.split('\s|,|x|X', tuple_str)
	tuple_str_arr = list(filter(None, tuple_str_arr))
	
	int_arr = []
	for tuple_str_i in tuple_str_arr:
		int_str = ''.join(filter(lambda x: x.isdigit(), tuple_str_i))
		
		if int_str == '':
			Log(ERR, 'Could not retrieve integer from ' + tuple_str_i + ' from "' + tuple_str + '"')
			int_str = '0'	
		
		int_arr.append(int(int_str))
		
	return tuple(int_arr)
	
def IsPosInt(x):
	return type(x) == int and x > 0

def IsValid2DSize(x):
	return type(x) == tuple and len(x) == 2 and IsPosInt(x[0]) and IsPosInt(x[1])

def AvgColor(c_list):
	c_list = tuple([t[i] for t in c_list] for i in range(len(c_list[0])))
	return tuple(sum(l)//len(l) for l in c_list)

def EqualizeTileBoundaries(im, crop_size):
	#Given an image and a crop size, make all pixels along the tile boundaries equal to each other
	#This step allows the user to use the output tiles with CreatePictureFromTiles.py
	#  such that a given can be combined with itself in strange and unusual ways.
	#Example: Output of a 3x3 pixel tile, where each number represents an unique color:
	#  - - - - - -
	# | 0 1 2 1 0 |
	# | 1 x x x 1 |
	# | 2 x x x 2 |
	# | 1 x x x 1 |
	# | 0 1 2 1 0 |
	#  - - - - - -

	if im == None or not IsValid2DSize(crop_size):
		return None
	
	#essentially a shallow pointer of pixel data
	pixels = im.load() 
	
	isSquare = crop_size[X] == crop_size[Y]
	im_width_in_tiles = im.size[X] // crop_size[X]
	im_height_in_tiles = im.size[Y] // crop_size[Y]
	
	#Average the color of all pixels residing on the crop boundaries
	#in an iterative fashion that prevents a pixel from being averaged more than once.
	for tile_y in range(im_height_in_tiles):
		for tile_x in range(im_width_in_tiles):
			tile_start_pos = (tile_x*crop_size[X], tile_y*crop_size[Y])
			tile_end_pos = (tile_start_pos[X] + crop_size[X]-1, tile_start_pos[Y] + crop_size[Y]-1)
			
			#For now, assume that the crop size is a perfect square. Handle rectangles later.
			if isSquare:
				for i in range(math.ceil(crop_size[X] / 2)):
					#Note: if (i == 0 or (i == len() - 1 and len() % 2 is not 0))
					#  Then technically only four pixels need to be averaged.
					#  However the math works out either way, 
					#    as (x1 + x2 + ... + xn) / n == (x1 + x2 + ... + xn + x1 + x2 + ... + xn) / 3*n
					c_list = [0]*8
					c_list[0] = pixels[tile_start_pos[X]+i, tile_start_pos[Y]]
					c_list[1] = pixels[tile_end_pos[X]-i,   tile_start_pos[Y]]
					c_list[2] = pixels[tile_start_pos[X],   tile_start_pos[Y]+i]
					c_list[3] = pixels[tile_end_pos[X],     tile_start_pos[Y]+i]
					c_list[4] = pixels[tile_start_pos[X],   tile_end_pos[Y]-i]
					c_list[5] = pixels[tile_end_pos[X],     tile_end_pos[Y]-i]
					c_list[6] = pixels[tile_start_pos[X]+i, tile_end_pos[Y]]
					c_list[7] = pixels[tile_end_pos[X]-i,   tile_end_pos[Y]]
					
					c = AvgColor(c_list)
					pixels[tile_start_pos[X]+i, tile_start_pos[Y]]   = c
					pixels[tile_end_pos[X]-i,   tile_start_pos[Y]]   = c
					pixels[tile_start_pos[X],   tile_start_pos[Y]+i] = c
					pixels[tile_end_pos[X],     tile_start_pos[Y]+i] = c
					pixels[tile_start_pos[X],   tile_end_pos[Y]-i]   = c
					pixels[tile_end_pos[X],     tile_end_pos[Y]-i]   = c
					pixels[tile_start_pos[X]+i, tile_end_pos[Y]]     = c
					pixels[tile_end_pos[X]-i,   tile_end_pos[Y]]     = c
			else:
				#For now, assume that the crop size is a perfect square. Handle rectangles later.
				pass
			
	
	return im
	
def DeblockAcrossTiles(im, crop_size):
	#Given an image and a crop size, average the colors across all tile boundaries
	#This step allows the user to use the output tiles with CreatePictureFromTiles.py
	#  such that an image can be put back together in the same manner that it was taken apart.
	#Example: Output of a 3x3 pixel tile, where each number represents an unique color:
	# 0   0 1 2   2
	#    - - - -
	# 0 | 0 1 2 | 2
	# 3 | 3 x 4 | 4
	# 5 | 5 6 7 | 7
	#    - - - - 
	# 5   5 6 7   7

	if im == None or not IsValid2DSize(crop_size):
		return None
	
	#essentially a shallow pointer of pixel data
	pixels = im.load() 
	
	im_width_in_tiles = im.size[X] // crop_size[X]
	im_height_in_tiles = im.size[Y] // crop_size[Y]

	#Average the color of all pixels residing on the crop boundaries
	#in an iterative fashion that prevents a pixel from being averaged more than once.
	for tile_y in range(im_height_in_tiles):
		for tile_x in range(im_width_in_tiles):
			tile_start_pos = (tile_x*crop_size[X], tile_y*crop_size[Y])
			tile_end_pos = (tile_start_pos[X] + crop_size[X]-1, tile_start_pos[Y] + crop_size[Y]-1)
			
			if tile_y < im_height_in_tiles - 1:
				#Average colors across the bottom boundary of the current tile,
				#Except for the bottom-left corner of the tile if this tile isn't left-most,
				#Except for the bottom-right corner of the tile if this tile isn't right-most.
				start_pos_x = tile_start_pos[X]+1
				end_pos_x = tile_end_pos[X]
				if tile_x == 0:
					start_pos_x -= 1
				if tile_x == im_width_in_tiles - 1:
					end_pos_x += 1
					
				for k in range(start_pos_x, end_pos_x):
					pixels[k,tile_end_pos[Y]] = AvgColor([pixels[k,tile_end_pos[Y]], pixels[k,tile_end_pos[Y]+1]])
					pixels[k,tile_end_pos[Y]+1] = pixels[k,tile_end_pos[Y]]
			
			if tile_x < im_width_in_tiles - 1:
				#Average colors across the right boundary of the current tile,
				#Except for the top-right corner of the tile if this tile isn't top-most,
				#Except for the bottom-right corner of the tile if this tile isn't bottom-most.
				start_pos_y = tile_start_pos[Y]+1
				end_pos_y = tile_end_pos[Y]
				if tile_y == 0:
					start_pos_y -= 1
				if tile_y == im_height_in_tiles - 1:
					end_pos_y += 1
					
				for k in range(start_pos_y, end_pos_y):
					pixels[tile_end_pos[X],k] = AvgColor([pixels[tile_end_pos[X],k], pixels[tile_end_pos[X]+1,k]])
					pixels[tile_end_pos[X]+1,k] = pixels[tile_end_pos[X],k]
			
			if tile_x < im_width_in_tiles - 1 and tile_y < im_height_in_tiles - 1:
				#Average the bottom-right most corner with its bottom, right, and bottom-right neighbors.
				c_list = [pixels[tile_end_pos[X],tile_end_pos[Y]],   pixels[tile_end_pos[X]+1, tile_end_pos[Y]],
						  pixels[tile_end_pos[X],tile_end_pos[Y]+1], pixels[tile_end_pos[X]+1, tile_end_pos[Y]+1]]
				c = AvgColor(c_list)
				pixels[tile_end_pos[X],tile_end_pos[Y]]   = pixels[tile_end_pos[X]+1, tile_end_pos[Y]]   = c
				pixels[tile_end_pos[X],tile_end_pos[Y]+1] = pixels[tile_end_pos[X]+1, tile_end_pos[Y]+1] = c

	return im
	
def Crop(im, crop_size):
	#Given an image, split it up into many smaller images across the boundaries made along the crop_size.
	#Output these images into the output directory path
	
	if im == None or not IsValid2DSize(crop_size):
		return {}
	
	im_width_in_tiles = im.size[X] // crop_size[X]
	im_height_in_tiles = im.size[Y] // crop_size[Y]
	
	tile_list = []
	for tile_y in range(im_height_in_tiles):
		for tile_x in range(im_width_in_tiles):
			start_pos = (tile_x*crop_size[X], tile_y*crop_size[Y])
			new_im = im.crop((start_pos[X], start_pos[Y], start_pos[X] + crop_size[X], start_pos[Y] + crop_size[Y]))
			
			tile_list.append(Tile(new_im, (tile_x, tile_y), tile_x + tile_y * im_width_in_tiles))
	
	return tile_list

def FindClusters(tile_list, num_clusters):
	if tile_list == [] or num_clusters < 2:
		return
	
	#Each row will have pixel data from one tile
	tile_data_matrix = []
	
	curr_tile_id = 0
	for tile in tile_list:
		if not (curr_tile_id == tile.id):
			Log(ERR, 'tile list is out of order, clustering will be incorrect')
			return
			
		#essentially a shallow pointer of pixel data
		pixels = tile.im.load()
		
		tile_data_array = []
		for pix_y in range(tile.im.size[Y]):
			for pix_x in range(tile.im.size[X]):
				pix_tup = pixels[pix_x, pix_y]
				tile_data_array += [pix_tup[R], pix_tup[G], pix_tup[B]]
			
		tile_data_matrix.append(tile_data_array)
		
		curr_tile_id += 1
	
	kmeans = KMeans(n_clusters = num_clusters, random_state = 0).fit(tile_data_matrix)
	for i, cluster_id in enumerate(kmeans.labels_):
		tile_list[i].cluster_id = cluster_id
	
	return

def SaveImages(tile_list, num_clusters, out_dir_path, in_im_filename, in_im_file_ext):
	if tile_list == []:
		return
	
	try:
		if not os.path.exists(out_dir_path):
			os.makedirs(out_dir_path)
		
		if num_clusters > 1:
			for i in range(num_clusters):
				os.makedirs(os.path.join(out_dir_path, str(i)))
	except OSError as e:
		Log(ERR, str(err))
		return []
	
	for tile in tile_list:
		new_im_file_name = in_im_filename + '_' + str(tile.y) + '_' + str(tile.x) + in_im_file_ext
		if num_clusters > 1:
			new_im_path = os.path.join(out_dir_path, str(tile.cluster_id), new_im_file_name)
		else:
			new_im_path = os.path.join(out_dir_path, new_im_file_name)
		
		try:
			tile.im.save(new_im_path)
		except OSError as err:
			Log(ERR, str(err))
			#If one save failed, the rest probably will also fail for the same reason.
			#As such, return now so that the log does not become full of error messages.
			Log(ERR, 'Halting crop operation due to file save error.')
			return

def Main():
	args = ParseCommandLineArgs()
	
	SetupLogging(args.log)
	
	in_im = GetImageFromPath(args.in_im_path)
	crop_size = GetTupleFromStr(args.crop_size)
	if not IsValid2DSize(crop_size):
		Log(ERR, 'crop size is "' + str(crop_size) + '", which is not a 2-tuple containing positive integers')
	
	try:
		if in_im.size[X] // crop_size[X] == 0 or in_im.size[Y] // crop_size[Y] == 0:
			Log(ERR, 'crop size of "' + str(crop_size) + '" does not fit into the input image size of ' + str(in_im.size))
	except AttributeError:
		pass
	
	#Deblock
	if args.dblk_mode == ACROSS_TILE_DBLK:
		dblk_im = DeblockAcrossTiles(in_im, crop_size)
	elif args.dblk_mode == EQUAL_BOUNDS_DBLK:
		#TODO: Remove this dumb for loop. Replace it with something less hacky.
		for i in range(10):
			dblk_im = EqualizeTileBoundaries(in_im, crop_size)
			dblk_im = DeblockAcrossTiles(in_im, crop_size)
	else:
		if args.dblk_mode is not NO_DBLK:
			Log(ERR, 'dblk_mode is "' + str(args.dblk_mode) + '", which is not an actual mode. No deblocking will be used.')
		dblk_im = in_im
		
	#Crop
	tile_list = Crop(dblk_im, crop_size)
	
	#Cluster
	FindClusters(tile_list, args.num_clusters)

	#Save
	(in_im_filename, in_im_file_ext) = os.path.splitext(args.in_im_path)
	SaveImages(tile_list, args.num_clusters, args.out_dir_path, in_im_filename, in_im_file_ext)
	
	CloseLog()
	
if __name__ == "__main__":
	Main()