# Development

Development requires [an environment configured for Rez 2](http://mydw.anim.dreamworks.com/display/SCM/Building+Python+Packages+for+Rez+2#BuildingPythonPackagesforRez2-Pre-releaseRez2Setup)

[Full Rez build, test and release instructions](http://mydw.anim.dreamworks.com/display/SCM/Building+Python+Packages+for+Rez+2)

1. Fork the repository on github
1. Clone it locally
1. Create a virtualenv in `~/.virtualenvs` for the project and [associate it with
   your editor](http://mydw.anim.dreamworks.com/display/TD/Using+PyCharm+for+Pipeline+Development#UsingPyCharmforPipelineDevelopment-UseyourvirtualenvinPyCharm).
   ``` bash
   rez-env buildtools -c "build-virtualenv"
   ```
1. Write code, following the [style guide](http://mydw.anim.dreamworks.com/display/STANDARDS/Python+Coding+Standards)
1. Build it
   ``` bash
   rez-env buildtools -c "rez-build --install"
   ```
1. Test it
   ``` bash
   rez-test render_profile_viewer
   ```
1. Update any manual documentation pages (like this one)
1. Test that the documentation builds without errors with:
   ``` bash
   rez-env buildtools -c "build-docs --fix-missing-mocks"
   ```
1. Commit all changes
1. Push to your fork
1. Make a pull request targeting the `develop` branch
