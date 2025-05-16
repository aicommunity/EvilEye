import matplotlib.pyplot as plt
import matplotlib.image as mpimg

# Load your images from files or URLs
img1 = mpimg.imread('Conf_height_1.png')
img2 = mpimg.imread('Conf_height_5.png')
img3 = mpimg.imread('Conf_height_3.png')
img4 = mpimg.imread('Conf_height_6.png')

fig, axs = plt.subplots(2, 2, figsize=(16, 12))

axs[0, 0].imshow(img1)
# axs[0, 0].set_title('Plot 1', pad=0, fontsize=18)
axs[0, 0].axis('off')

axs[0, 1].imshow(img2)
# axs[0, 1].set_title('Plot 2', pad=0, fontsize=18)
axs[0, 1].axis('off')

axs[1, 0].imshow(img3)
# axs[1, 0].set_title('Plot 3', pad=0, fontsize=18)
axs[1, 0].axis('off')

axs[1, 1].imshow(img4)
# axs[1, 1].set_title('Plot 4', pad=0, fontsize=18)
axs[1, 1].axis('off')

plt.subplots_adjust(wspace=0.05, hspace=0.05)

# Use tight_layout to further minimize white space
plt.tight_layout(pad=0.5)
fig.subplots_adjust(top=0.95)
plt.savefig('combined_plots.png', dpi=300, bbox_inches='tight')
plt.show()