program matrix_multiplication
    implicit none
    integer :: N, L, M 
    integer :: iostat, i, j, k, temp1, temp2 
    real, dimension(:, :), allocatable :: mat1, mat2, prod_mat
    character(len=24) :: file1, file2 
    character(len=100) :: iomsg 

    ! Read the filename containing matrix one and matrix two
    write (*,1000) 
    1000 format(1x, 'This program calculate the product of two ',/, & 
                1x, 'matrix from input file. ',/, &
                    'Type filename containing first matrx: ')
    read (*,'(A24)') file1
    
    write (*, 1010)
    1010 format(1x, 'Type filename containing second matrix: ')
    read (*,*) file2 

    open(unit=10, file=file1, status='old', action='read', iostat=iostat, iomsg=iomsg)
    if (iostat /= 0) then 
        write (*,1030) iostat, iomsg
        1030 format(1x, '--- Error opening file. --- Iostat : ', I4,/, &
                    1x, 'Message: ', A)
        stop 
    end if 

    open(unit=20, file=file2, status='old', action='read', iostat=iostat, iomsg=iomsg)
    if (iostat /= 0) then 
        write (*,1040) iostat, iomsg
        1040 format(1x, '--- Error opening file. --- Iostat : ', I4,/, &
                    1x, 'Message: ', A)
        stop 
    end if 

    read (10,*) N, temp1
    read (20,*) temp2, M

    if (temp1 /=  temp2 ) then 
        write (*,*) ' Size not compatible. Existing program.'
        stop 
    else 
        L = temp1 
        allocate(mat1(N, L), mat2(L, M), prod_mat(N, M), stat=iostat)

        if (iostat /= 0) stop 

        ! Load matrix1 and matrix2 from file into array
        do i = 1, N 
            read (10,*) (mat1(i, j), j = 1, L)
        end do 

        do i = 1, L
            read (20,*) (mat2(i, j), j = 1, M)
        end do 

        ! Calculate the product of two matrix 
        prod_mat = 0.0
        do i = 1, N
            do j = 1, M 
                do k = 1, L 
                    prod_mat(i,j) = prod_mat(i, j) + (mat1(i, k) * mat2(k, j))
                end do 
            end do 
        end do 
    end if 

    ! Print product of matrix 1 and 2 
    write (*,*) ' Product of matrix 1 and 2 is : '
    do i = 1, N 
        write (*, 1050) (prod_mat(i, j), j = 1, M)
        1050 format(1x, 100F12.3)
    end do 

end program matrix_multiplication