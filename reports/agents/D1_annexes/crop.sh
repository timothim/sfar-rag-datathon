#!/bin/bash
# crop.sh pdf page x0 y0 x1 y1 out  (points) -> 250 dpi crop with padding
pdf=$1; pg=$2; k=250/72
x=$(echo "($3-15)*$k" | bc); y=$(echo "($4-8)*$k" | bc); W=$(echo "($5-$3+30)*$k" | bc); H=$(echo "($6-$4+16)*$k" | bc)
pdftoppm -f $pg -l $pg -r 250 -x ${x%.*} -y ${y%.*} -W ${W%.*} -H ${H%.*} -png -singlefile "$pdf" "$7"
