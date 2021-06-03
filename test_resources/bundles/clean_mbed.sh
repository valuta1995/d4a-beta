sed -i -- 's/-Wl,--wrap,vfprintf //g' ./*/Makefile
sed -i -- 's/-Wl,--wrap,vsnprintf //g' ./*/Makefile

