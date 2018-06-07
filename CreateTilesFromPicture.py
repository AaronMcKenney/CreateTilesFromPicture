from PIL import Image
import argparse
import os
import os.path
import re

LOG_NAME = 'CreateTilesFromPicture_LOG.txt'
WARN = 'WARN'
ERR = 'ERR'

X = 0
Y = 1

g_do_log = False
g_log_file = None

def ParseCommandLineArgs():
	size_def = '(0,0)'
	in_def = './in.png'
	out_def = './out'
	log_def = False
	
	prog_desc = ('Given a path to an image, ' 
		'as well as a crop size in terms of (width in pixels, height in pixels), ' 
		'take apart a picture, and create multiple "tiles", '
		'which will be deposited in the given out directory. '
		'NOTE 1: If the image size is not divisible by the crop size, "partial tiles" will not be output. '
		'NOTE 2: This program will not produce good results for lossy codecs such as jpeg')
	size_help = ('The width and height (comma-separated) of each tile to be taken from the image. '
		'Example formats: "1,2", "(1,2)". ')
	in_help = ('Path to the image that will have tiles made out of it. '
		'The name should include the extension, which dictates the image format of the output. '
		'Default: ' + in_def)
	out_help = ('Path to the directory which will contain the output tiles. '
		'Default: ' + out_def)
	log_help = ('If set, log warnings and errors to "' + LOG_NAME + '" file. '
		'If not set, only report errors to stdout. '
		'Default: ' + str(log_def))
	no_log_help = ('If set, disable logging. Default: ' + str(not log_def))
	
	parser = argparse.ArgumentParser(description = prog_desc)
	parser.add_argument('--crop_size',    '-s', type = str,                           help = size_help)
	parser.add_argument('--in_im_path',   '-i', type = str,                           help = in_help)
	parser.add_argument('--out_dir_path', '-o', type = str,                           help = out_help)
	parser.add_argument('--log',          '-l', dest = 'log', action = 'store_true',  help = log_help)
	parser.add_argument('--no-log',             dest = 'log', action = 'store_false', help = no_log_help)
	
	parser.set_defaults(crop_size = size_def, in_im_path = in_def, out_dir_path = out_def, log = log_def)

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
	tuple_str_arr = re.split('\s|,', tuple_str)
	
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
	
def Deblock(im, crop_size):
	#Given an image and a crop size, average the colors across all tile boundaries
	#This is step allows the user to use the output tiles with CreatePictureFromTiles.py

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
			start_pos = (tile_x*crop_size[X], tile_y*crop_size[Y])
			end_pos = (start_pos[X] + crop_size[X]-1, start_pos[Y] + crop_size[Y]-1)
			
			if tile_y < im_height_in_tiles - 1:
				#Average colors across the bottom boundary of the current tile,
				#Except for the bottom-left corner of the tile if this tile isn't left-most,
				#Except for the bottom-right corner of the tile if this tile isn't right-most.
				start_pos_x = start_pos[X]+1
				end_pos_x = end_pos[X]
				if tile_x == 0:
					start_pos_x -= 1
				if tile_x == im_width_in_tiles - 1:
					end_pos_x += 1
					
				for k in range(start_pos_x, end_pos_x):
					pixels[k,end_pos[Y]] = AvgColor([pixels[k,end_pos[Y]], pixels[k,end_pos[Y]+1]])
					pixels[k,end_pos[Y]+1] = pixels[k,end_pos[Y]]
			
			if tile_x < im_width_in_tiles - 1:
				#Average colors across the right boundary of the current tile,
				#Except for the top-right corner of the tile if this tile isn't top-most,
				#Except for the bottom-right corner of the tile if this tile isn't bottom-most.
				start_pos_y = start_pos[Y]+1
				end_pos_y = end_pos[Y]
				if tile_y == 0:
					start_pos_y -= 1
				if tile_y == im_height_in_tiles - 1:
					end_pos_y += 1
					
				for k in range(start_pos_y, end_pos_y):
					pixels[end_pos[X],k] = AvgColor([pixels[end_pos[X],k], pixels[end_pos[X]+1,k]])
					pixels[end_pos[X]+1,k] = pixels[end_pos[X],k]
			
			if tile_x < im_width_in_tiles - 1 and tile_y < im_height_in_tiles - 1:
				#Average the bottom-right most corner with its bottom, right, and bottom-right neighbors.
				c_list = [pixels[end_pos[X],end_pos[Y]],   pixels[end_pos[X]+1, end_pos[Y]],
						  pixels[end_pos[X],end_pos[Y]+1], pixels[end_pos[X]+1, end_pos[Y]+1]]
				c = AvgColor(c_list)
				pixels[end_pos[X],end_pos[Y]]   = pixels[end_pos[X]+1, end_pos[Y]]   = c
				pixels[end_pos[X],end_pos[Y]+1] = pixels[end_pos[X]+1, end_pos[Y]+1] = c

	return im

def Crop(im, crop_size, out_dir_path, in_im_filename, in_im_file_ext):
	#Given an image, split it up into many smaller images across the boundaries made along the crop_size.
	#Output these images into the output directory path
	
	if im == None or not IsValid2DSize(crop_size):
		return
	
	try:
		if not os.path.exists(out_dir_path):
			os.makedirs(out_dir_path)
	except OSError as e:
		Log(ERR, str(err))
		return
	
	im_width_in_tiles = im.size[X] // crop_size[X]
	im_height_in_tiles = im.size[Y] // crop_size[Y]
	
	for tile_y in range(im_height_in_tiles):
		for tile_x in range(im_width_in_tiles):
			start_pos = (tile_x*crop_size[X], tile_y*crop_size[Y])
			new_im = im.crop((start_pos[X], start_pos[Y], start_pos[X] + crop_size[X], start_pos[Y] + crop_size[Y]))
			
			new_im_path = os.path.join(out_dir_path, in_im_filename) + '_' + str(tile_y) + '_' + str(tile_x) + in_im_file_ext
			try:
				new_im.save(new_im_path)
			except OSError as err:
				Log(ERR, str(err))
				#If one save failed, the rest probably will also fail for the same reason.
				#As such, return now so that the log does not become full of error messages.
				Log(ERR, 'Halting crop operation due to file save error.')
				return
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
	
	dblk_im = Deblock(in_im, crop_size)
	(in_im_filename, in_im_file_ext) = os.path.splitext(args.in_im_path)
	Crop(dblk_im, crop_size, args.out_dir_path, in_im_filename, in_im_file_ext)

	CloseLog()
	
if __name__ == "__main__":
	Main()