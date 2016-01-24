from setuptools import setup
import sys


setup(name='ansaconv',
      version='0.1',
      description='Convert ANSI art primarily for display in a terminal emulator',
      url='http://github.com/ajsalminen/ansaconv',
      author='Antti J. Salminen',
      author_email='mail-projects.ansaconv@facingworlds.com',
      license='MIT',
      entry_points={
          'console_scripts': [
              'ansaconv = ansi_art_converter:main'
          ],
      },
      packages=['ansi_art_converter'],
      zip_safe=False,
      include_package_data=False)
