program sum_of_array_elements
    implicit none
    integer :: NROW, NCOL 
    real,dimension(:,:), allocatable :: arr 
    real, dimension(:), allocatable :: sum_row_i, sum_col_i
    integer :: iostat, alloc_stat, i, j 
    character(len=24) :: filename
    character(len=100) :: iomsg 

    ! Read filename
    write(*,1000) 
    1000 format(1x, 'This program calculate the some of each elements in an given array.',/,&
                    ' Enter the filename : ')
    read (*,'(A24)') filename
    
    ! Open Input File
    open (unit=10, file=filename, status='OLD', action='READ', iostat=iostat, iomsg=iomsg)

    if (iostat /= 0) then
        write (*,1010) iostat, iomsg
        1010 format(1x, '--- Error opening file. Iostat = ', I4,/, &
                        '--- Message : ', A) 

        stop
    else
        ! Read how-many rows and column the array have
        read (10, *) NROW, NCOL

        allocate(arr(NROW, NCOL), sum_row_i(NROW), sum_col_i(NCOL), stat=alloc_stat)

        if (alloc_stat /= 0) stop 
        
        do i = 1, NROW 
            read (10, *) (arr(i, j), j = 1, NCOL)
        end do 
    end if 

    do i = 1, NROW 
        sum_row_i(i) = sum(arr(i,:))
    end do 

    do i = 1, NCOL
        sum_col_i(i) = sum(arr(:,i))
    end do 

    write (*,1020)  (i, sum_row_i(i), i = 1, NROW)
    1020 format(1x, 'Sum of the row ', i3,'  = ', F10.4)

    write (*,1030)  (i, sum_col_i(i), i = 1, NCOL)
    1030 format(1x, 'Sum of the col ', i3,'  = ', F10.4)

    deallocate(arr)

end program sum_of_array_elements