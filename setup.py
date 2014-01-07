from setuptools import setup, find_packages
import sys, os

version = '0.6.11'

setup(
	name='ckanext-dgvat',
	version=version,
	description="data.gv.at extension",
	long_description="""\
	""",
	classifiers=[], # Get strings from http://pypi.python.org/pypi?%3Aaction=list_classifiers
	keywords='',
	author='BRZ gmbH',
	author_email='data@brz.gv.at',
	url='www.brz.gv.at',
	license='GPL',
	packages=find_packages(exclude=['ez_setup', 'examples', 'tests']),
	namespace_packages=['ckanext', 'ckanext.dgvat'],
	include_package_data=True,
	zip_safe=False,
	install_requires=[
		# -*- Extra requirements: -*-
	],
	entry_points=
	"""
        [ckan.plugins]
        datagvat = ckanext.dgvat.plugin:DgvatForm

	   # [ckan.forms]
       # package_gov3 = ckanext.dgvat.forms.data_gv_at:get_dgvat_fieldset
	""",
)
