%global pypi_name triton

# For testing
%bcond_with test

# Rebuilding clang is slow, do
# export LLVM_SYSPATH=/path-to/llvm-project-install
# export PYBIND11_SYSPATH=/path-to/pybind11-project-install
%bcond_without local
%if %{with local}
%global _lto_cflags %nil
# For debugging
%bcond_without debug
%else
%bcond_with debug
%endif

# release/2.3.x - 4/24/23
%global commit0 54d0bb9e4b2e2dab7dc899008c0f14915f665a2f
# from python/setup.py
%global commit1 c5dede880d175f7229c9b2923f4753e12702305d
%global pypi_version 2.3.0

%global shortcommit0 %(c=%{commit0}; echo ${c:0:7})
%global shortcommit1 %(c=%{commit1}; echo ${c:0:7})

# The llvm build has its LLVM_PARALLEL_COMPILE|LINK_JOBS switches
# Triton uses the envionment variable MAX_JOBS for both.
%global _smp_mflags %{nil}

%global toolchain gcc

Name:           python-%{pypi_name}-rocm
Version:        %{pypi_version}
Release:        1%{?dist}
Summary:        A language and compiler for custom Deep Learning operations

License:        MIT AND Apache-2.0 AND BSD-3-Clause AND BSD-2-Clause 
# Main license is MIT
# llvm is Apache-2.0, BSD-3-Clause AND BSD-2-Clause 

URL:            https://github.com/ROCm/triton/
Source0:        %{url}/archive/%{commit0}/triton-%{shortcommit0}.tar.gz
%if %{without local}
Source1:        https://github.com/llvm/llvm-project/archive/%{commit1}.tar.gz
Source2:        https://github.com/pybind/pybind11/archive/refs/tags/v2.11.1.tar.gz
%endif

Patch1:         0001-disable-tma-on-rocm.patch
Patch2:         0001-remove-ptxas.patch
# Can not download things
# Patch1:         0001-Prepare-triton-setup-for-fedora.patch
# TBD: Add PR
# Patch2:         0001-Add-a-fallback-to-the-location-of-the-ROCm-linker.patch
# Not sure if AMD's rpm still includes cuda2gcn.bc, we do not.
# Patch3:         0001-Remove-cuda2gcn-from-bc-list.patch
# A problem with mallocing
# Patch4:         0001-relock-gil.patch

# GPUs really only work on x86_64
ExclusiveArch:  x86_64

BuildRequires:  gcc-c++
BuildRequires:  cmake
BuildRequires:  ninja-build
BuildRequires:	zlib-devel
BuildRequires:  python3-devel
BuildRequires:  python3dist(filelock)
BuildRequires:  python3dist(pip)
BuildRequires:  python3dist(pytest)
BuildRequires:  python3dist(setuptools)
BuildRequires:  python3dist(wheel)

# Triton uses a custom snapshot of the in development llvm
# Because of instablity of the llvm api, we must use the one
# triton uses.  llvm is statically built and none of the
# llvm headers or libraries are distributed directly.
Provides:       bundled(llvm-project) = 17.0.0.g%{shortcommit1}
Provides:       bundled(pybind11) = 2.11.1

Requires:       rocm-comgr-devel
Requires:       rocm-device-libs-devel
Requires:       rocm-runtime-devel

%description
Triton is a language and compiler for writing highly efficient custom
Deep-Learning primitives. The aim of Triton is to provide an open-source
environment to write fast code at higher productivity than CUDA, but
also with higher flexibility than other existing DSLs.

%package -n     python3-%{pypi_name}-rocm
Summary:        %{summary}

%description -n python3-%{pypi_name}-rocm
Triton is a language and compiler for writing highly efficient custom
Deep-Learning primitives. The aim of Triton is to provide an open-source
environment to write fast code at higher productivity than CUDA, but
also with higher flexibility than other existing DSLs.

%prep
%autosetup -p1 -n triton-%{commit0}
%if %{without local}
# LLVM
tar xf %{SOURCE1}
# PyBind
tar xf %{SOURCE2}
%endif

# Remove bundled egg-info
rm -rf python/*.egg-info

# Remove cuda
rm -rf python/triton/third_party/cuda

# Remove and replace packaged hip bits
rm -rf python/triton/third_party/hip/lib/hsa/*
sed -i -e 's@lib/libhsa-runtime64.so@lib64/libhsa-runtime64.so@g' CMakeLists.txt
# cd python/triton/third_party/hip/lib/hsa
# ln -s %{_libdir}/libhsa-runtime64.so* .
# cd -
rm -rf python/triton/third_party/hip/lib/bitcode/*
cd python/triton/third_party/hip/lib/bitcode/
HIP_CLANG_PATH=`hipconfig -l`
RESOURCE_DIR=`${HIP_CLANG_PATH}/clang -print-resource-dir`
ln -s ${RESOURCE_DIR}/amdgcn/bitcode/* .
cd -

%if %{without local}
# rm llvm-project bits we do not need
rm -rf llvm-project-%{commit1}/{bolt,clang,compiler-rt,flang,libc,libclc,libcxx,libcxxabi,libunwind,lld,lldb,llvm-libgcc,openmp,polly,pst,runtimes,utils}
%endif

# Disable download
sed -i -e '/^download_and_copy_ptxas/d' python/setup.py
# Lie about the version
sed -i -e 's@version="2.2.0",@version="2.3.0",@' python/setup.py

# For debugging
%if %{with debug}
sed -i -e 's@${CMAKE_C_FLAGS} -D__STDC_FORMAT_MACROS @-O1 -g -D__STDC_FORMAT_MACROS @' CMakeLists.txt
%endif

%if %{without test}
# no knob to turn off downloading of googletest
sed -i -e 's@add_subdirectory(unittest)@#add_subdirectory(unittest)@' CMakeLists.txt
%else
# E   ValueError: option names {'--device'} already added
sed -i -e 's@--device@--ddevice@' python/test/unit/operators/conftest.py
# performance is only nvidia
rm python/test/regression/test_performance.py
# E   ModuleNotFoundError: No module named 'triton.common'
rm python/test/backend/test_device_backend.py
%endif

# disable -Werror
sed -i -e 's@-Werror @ @' CMakeLists.txt

# change default rocm location
sed -i -e 's@set(ROCM_DEFAULT_DIR "/opt/rocm")@set(ROCM_DEFAULT_DIR "/usr")@' CMakeLists.txt

# just removed cuda.h, can not use it now
sed -i -e '/cuda.h/d'  include/triton/Target/PTX/TmaMetadata.h


%build

# Real cores, No hyperthreading
COMPILE_JOBS=`cat /proc/cpuinfo | grep -m 1 'cpu cores' | awk '{ print $4 }'`
if [ ${COMPILE_JOBS}x = x ]; then
    COMPILE_JOBS=1
fi
# Take into account memmory usage per core, do not thrash real memory
BUILD_MEM=2
MEM_KB=0
MEM_KB=`cat /proc/meminfo | grep MemTotal | awk '{ print $2 }'`
MEM_MB=`eval "expr ${MEM_KB} / 1024"`
MEM_GB=`eval "expr ${MEM_MB} / 1024"`
COMPILE_JOBS_MEM=`eval "expr 1 + ${MEM_GB} / ${BUILD_MEM}"`
if [ "$COMPILE_JOBS_MEM" -lt "$COMPILE_JOBS" ]; then
    COMPILE_JOBS=$COMPILE_JOBS_MEM
fi
LINK_MEM=32
LINK_JOBS=`eval "expr 1 + ${MEM_GB} / ${LINK_MEM}"`

%if %{without local}

cd llvm-project-%{commit1}

%cmake -G Ninja \
       -DBUILD_SHARED_LIBS=OFF \
       -DCMAKE_BUILD_TYPE=Release \
       -DCMAKE_INSTALL_PREFIX=$PWD/install \
       -DLLVM_ENABLE_PROJECTS="mlir;llvm" \
       -DLLVM_PARALLEL_COMPILE_JOBS=$COMPILE_JOBS \
       -DLLVM_PARALLEL_LINK_JOBS=$LINK_JOBS \
       -DLLVM_TARGETS_TO_BUILD="X86;AMDGPU;NVPTX" \
       llvm
%cmake_build
%cmake_build -t install

export LLVM_SYSPATH=$PWD/install
cd ..

cd pybind11-2.11.1
%cmake -G Ninja \
       -DBUILD_SHARED_LIBS=OFF \
       -DCMAKE_BUILD_TYPE=Release \
       -DCMAKE_INSTALL_PREFIX=$PWD/install \
       -DPYBIND11_TEST=OFF

%cmake_build
%cmake_build -t install

export PYBIND11_SYSPATH=$PWD/install
cd ..

%endif

export PATH=$LLVM_SYSPATH/bin:$PATH

%if %{with debug}
export DEBUG=1
%else
export REL_WITH_DEB_INFO=1
%endif

export CC=gcc
export CXX=g++
export MAX_JOBS=$LINK_JOBS

cd python
%py3_build

%install
cd python
%py3_install

%if %{with rocm}
module purge
%endif

# empty files
rm %{buildroot}%{python3_sitearch}/triton/compiler/make_launcher.py


# Unit tests download so are not suitable for mock
%if %{with test}
%check
cd python
module load rocm/gfx9
export PYTHONPATH=/usr/lib64/rocm/gfx9/lib64/python3.12/site-packages/
%pytest
module purge
#cd llvm-project-%{commit1}
#%cmake_build -t test
%endif

%files -n python3-%{pypi_name}-rocm
%{python3_sitearch}/%{pypi_name}
%{python3_sitearch}/%{pypi_name}*.egg-info

%changelog
* Wed Feb 14 2024 Tom Rix <trix@redhat.com> 3.0.0-1
- Inital release



